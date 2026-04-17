#!/usr/bin/env python3
"""
main.py
Entry point for the RFID ↔ LTE gateway.

Run routine:
  1. Initialise ThingMagic 6e reader
  2. Open PicoLTE serial link
  3. Loop: collect tags for a window → build events → send (WiFi / LTE)

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
)
from tm6e      import connect_reader, epc_to_str, read_user_memory, build_event
from pico_lte  import open_pico_serial, send_events_lte
from wifi       import send_events_wifi


# ─────────────────────────────────────────────────────────────────────────────
#  GRACEFUL SHUTDOWN
# ─────────────────────────────────────────────────────────────────────────────

shutdown = Event()                      # thread-safe flag, replaces `_run` global


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
    """
    WiFi first, LTE second.
    If FORCE_LTE is True, skip WiFi entirely.
    """
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
#  MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    reader   = None          # mercury.Reader
    pico_ser = None          # serial.Serial

    try:
        # ── 1. Connect to RFID reader ─────────────────────────────────────
        reader = connect_reader()

        # ── 2. Connect to PicoLTE ─────────────────────────────────────────
        pico_ser = open_pico_serial(shutdown)

        print(f"\n[INFO] Window: {READ_WINDOW_SECS}s | "
              f"Tags: {len(ALLOWED_TAGS)} | "
              f"Force LTE: {FORCE_LTE} | "
              f"Require user memory: {REQUIRE_USER_MEMORY}")
        print("[INFO] Ctrl+C to stop.\n")

        # ── 3. Main collection loop ───────────────────────────────────────
        while not shutdown.is_set():
            window_start = time.time()
            unique_tags: Dict[str, dict] = {}

            print(f"[INFO] ── Window opened {datetime.now():%H:%M:%S} "
                  f"(collecting for {READ_WINDOW_SECS}s) ──")

            # 3a. Collect until window expires
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

            # 3b. Build one event per unique EPC
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

            # 3c. Apply REQUIRE_USER_MEMORY filter
            if REQUIRE_USER_MEMORY:
                filtered   = [e for e in events if e.get("userMemory") is not None]
                suppressed = len(events) - len(filtered)
                if suppressed:
                    print(f"[INFO] {suppressed} event(s) suppressed — no user memory read.")
            else:
                filtered = events

            if not filtered:
                print("[INFO] No events passed filter.\n")
                continue

            # 3d. Send — WiFi first, LTE fallback
            #send_with_fallback(filtered, pico_ser)
            #print()

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