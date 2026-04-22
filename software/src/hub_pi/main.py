#!/usr/bin/env python3
"""
main.py
Entry point for the RFID <-> LTE gateway.

Run routine:
  1. Initialise ThingMagic 6e reader
  2. Open PicoLTE serial link
  3. Send one hub sensor reading (temperature, humidity, light)
  4. Loop: collect tags for a window -> build events -> send (WiFi / LTE)

Designed to be started automatically by the Pi on boot (see systemd unit).
"""

import signal
import sys
import time
from datetime import datetime
from threading import Event
from typing import Dict, List, Optional

import serial

# ── Project modules ───────────────────────────────────────────────────────────
from config import (
    ALLOWED_TAGS,
    FORCE_LTE,
    READ_WINDOW_MS,
    READ_WINDOW_SECS,
    REQUIRE_USER_MEMORY,
    USER_MEM_WORDS,
    TEST_DATA,
)
from tm6e         import connect_reader, epc_to_str, read_user_memory, build_event
from pico_lte     import open_pico_serial, send_events_lte
from wifi         import send_events_wifi
from event_sender import send_rfid_events, send_hub_reading


# ─────────────────────────────────────────────────────────────────────────────
#  GRACEFUL SHUTDOWN
# ─────────────────────────────────────────────────────────────────────────────

shutdown = Event()                      # thread-safe flag


def _on_signal(sig, _frame) -> None:
    print("\n[INFO] Shutdown signal received...")
    shutdown.set()


signal.signal(signal.SIGINT,  _on_signal)
signal.signal(signal.SIGTERM, _on_signal)


# ─────────────────────────────────────────────────────────────────────────────
#  FALLBACK LOGIC
# ─────────────────────────────────────────────────────────────────────────────

def send_with_fallback(events: List[dict],
                       pico_ser: Optional[serial.Serial]) -> bool:
    """WiFi first, LTE second.  If FORCE_LTE is True, skip WiFi entirely."""
    if not FORCE_LTE:
        if send_events_wifi(events):
            return True
        print("[INFO] WiFi failed — falling back to LTE.")
    else:
        print("[INFO] FORCE_LTE=True — skipping WiFi.")

    if pico_ser is None or not pico_ser.is_open:
        print("[WARN] Pico serial unavailable — cannot send via LTE.")
        return False

    return send_events_lte(events, pico_ser)


# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _apply_filter(events: List[dict]) -> List[dict]:
    """Apply REQUIRE_USER_MEMORY filter and log any suppressed events."""
    if not REQUIRE_USER_MEMORY:
        return events
    filtered   = [e for e in events if e.get("userMemory")]
    suppressed = len(events) - len(filtered)
    if suppressed:
        print(f"[INFO] {suppressed} event(s) suppressed — no user memory read.")
    return filtered


def _strip_user_memory_spaces(events: List[dict]) -> None:
    """Remove whitespace from userMemory fields in-place (test JSON may have them)."""
    for e in events:
        if e.get("userMemory"):
            e["userMemory"] = e["userMemory"].replace(" ", "")


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    reader   = None          # mercury.Reader
    pico_ser = None          # serial.Serial

    try:
        # ── 1. Connect to RFID reader ─────────────────────────────────────
        if not TEST_DATA:
            reader = connect_reader()

        # ── 2. Connect to PicoLTE ─────────────────────────────────────────
        pico_ser = open_pico_serial(shutdown)

        print(f"\n[INFO] Window: {READ_WINDOW_SECS}s | "
              f"Tags: {len(ALLOWED_TAGS)} | "
              f"Force LTE: {FORCE_LTE} | "
              f"Require user memory: {REQUIRE_USER_MEMORY} | "
              f"Test data: {TEST_DATA}")
        print("[INFO] Ctrl+C to stop.\n")

        # ── 3. Send hub sensor reading ────────────────────────────────────
        print("[INFO] ── Sampling hub sensors ──")
        send_hub_reading(pico_ser)
        print()

        # ── 4a. TEST path — load events from JSON file and send once ──────
        if TEST_DATA:
            import json

            print("[TEST] Loading events from test_data.json ...")
            with open("test_data.json", "r") as f:
                raw_events: List[dict] = json.load(f)

            _strip_user_memory_spaces(raw_events)

            now_iso = datetime.now().isoformat(timespec="milliseconds")
            for e in raw_events:
                e["timestamp"] = now_iso

            print(f"[TEST] {len(raw_events)} event(s) loaded:")
            for e in raw_events:
                print(f"       EPC:{e.get('epc')}  "
                      f"userMemory:{e.get('userMemory')}  "
                      f"rssi:{e.get('rssi')}  "
                      f"antenna:{e.get('antennaId')}")
            print()

            filtered = _apply_filter(raw_events)
            if not filtered:
                print("[INFO] No events passed filter.")
            else:
                send_rfid_events(filtered, pico_ser)
            print()
            return                          # exit cleanly after one test send

        # ── 4b. LIVE path — continuous read / send loop ───────────────────
        while not shutdown.is_set():
            window_start = time.time()
            unique_tags: Dict[str, dict] = {}

            print(f"[INFO] ── Window opened {datetime.now():%H:%M:%S} "
                  f"(collecting for {READ_WINDOW_SECS}s) ──")

            # Collect until window expires
            while not shutdown.is_set() and (time.time() - window_start) < READ_WINDOW_SECS:
                try:
                    tags_now = reader.read(READ_WINDOW_MS)
                except Exception as ex:
                    print(f"[WARN] Read error: {ex}")
                    tags_now = []

                now = datetime.now()

                for tag in tags_now:
                    epc = epc_to_str(tag.epc)
                    if epc not in ALLOWED_TAGS:
                        continue

                    if epc not in unique_tags:
                        rssi    = getattr(tag, "rssi",    None)
                        antenna = getattr(tag, "antenna", None)
                        unique_tags[epc] = {
                            "ts":            now,
                            "rssi":          rssi,
                            "antenna":       antenna,
                            "user_mem":      None,
                            "user_mem_read": False,
                        }
                        print(f"{now:%H:%M:%S}  [TAG]  EPC:{epc}  "
                              f"RSSI:{rssi}  ANT:{antenna}")

                    # Retry user memory every cycle until success
                    if not unique_tags[epc]["user_mem_read"]:
                        user_hex = read_user_memory(reader, epc)
                        if user_hex:
                            unique_tags[epc]["user_mem"]      = user_hex
                            unique_tags[epc]["user_mem_read"] = True
                            print(f"           USER[0..{USER_MEM_WORDS - 1}] = {user_hex}")

                time.sleep(0.05)

            # Build one event per unique EPC
            print(f"[INFO] Window closed — {len(unique_tags)} unique tag(s) detected.")

            events: List[dict] = [
                build_event(
                    "ENTER", epc, data["ts"],
                    user_memory=data["user_mem"],
                    rssi=data["rssi"],
                    antenna_id=data["antenna"],
                )
                for epc, data in unique_tags.items()
            ]

            if not events:
                print("[INFO] No events to send.\n")
                continue

            filtered = _apply_filter(events)
            if not filtered:
                print("[INFO] No events passed filter.\n")
                continue

            send_rfid_events(filtered, pico_ser)
            print()

    except Exception as ex:
        print(f"\n[ERROR] Fatal: {ex}", file=sys.stderr)
        raise

    finally:
        print("[INFO] Cleaning up...")
        if reader:
            try:
                reader.destroy()
            except Exception:
                pass
        if pico_ser and pico_ser.is_open:
            try:
                pico_ser.close()
            except Exception:
                pass
        time.sleep(0.2)
        print("[INFO] Stopped.")


if __name__ == "__main__":
    main()