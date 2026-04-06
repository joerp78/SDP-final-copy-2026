#!/usr/bin/env python3
"""
rfid_reader.py
Raspberry Pi 3B + ThingMagic 6e Micro (USB)

Collects RFID reads over a fixed window then sends to the server via WiFi
with automatic LTE fallback through a Sixfab PicoLTE on /dev/ttyACM1.
"""

import json
import signal
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional

import mercury
import requests
import serial                          # pip install pyserial


# ─────────────────────────────────────────────────────────────────────────────
#  CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

READER_URI       = "tmr:///dev/ttyACM0"
READER_BAUDRATE  = 115200
REGION           = "NA2"
ANTENNA_PORT     = 1
READ_POWER_CDBM  = 2500
READ_WINDOW_MS   = 500                 # Milliseconds per blocking read call
READ_WINDOW_SECS = 30                  # Total collection window in seconds
USER_MEM_WORDS   = 4
USER_MEM_RETRIES = 8
USER_MEM_DELAY   = 0.15

API_URL          = "https://joepaola.com/sdp/api/events"
API_TIMEOUT_SEC  = 10

REQUIRE_USER_MEMORY = True             # True = only send events that have user memory

# ── LTE / PicoLTE ─────────────────────────────────────────────────────────────
FORCE_LTE        = True               # True = skip WiFi, always send via LTE
PICO_PORT        = "/dev/ttyACM1"      # Serial port for Sixfab PicoLTE
PICO_BAUD        = 115200
PICO_TIMEOUT_SEC = 60                  # How long to wait for Pico LTE response

ALLOWED_TAGS = {
    "0080B0443C00000012787622",
    "0080B0443C00000012787627",
}


# ─────────────────────────────────────────────────────────────────────────────
#  SIGNAL HANDLING
# ─────────────────────────────────────────────────────────────────────────────

_run: bool = True

def _on_signal(sig, frame) -> None:
    global _run
    print("\n[INFO] Shutdown signal received...")
    _run = False

signal.signal(signal.SIGINT,  _on_signal)
signal.signal(signal.SIGTERM, _on_signal)


# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────

_HEX_CHARS = set(b'0123456789ABCDEFabcdef')

def epc_to_str(epc) -> str:
    if isinstance(epc, (bytes, bytearray)):
        if epc and all(b in _HEX_CHARS for b in epc):
            return epc.decode('ascii').upper()
        return epc.hex().upper()
    return str(epc).replace(":", "").replace(" ", "").upper()


def read_user_memory(reader: mercury.Reader, epc_hex: str) -> Optional[str]:
    """
    Read USER memory bank with EPC filter.
    Tries ASCII-encoded EPC first (Linux ThingMagic quirk), then raw binary.
    """
    last_ex: Optional[Exception] = None
    epc_filter_variants = [
        epc_hex.encode('ascii'),    # b'0080B0443C...' — try first
        bytes.fromhex(epc_hex),     # b'\x00\x80\xb0\x44...' — fallback
    ]

    time.sleep(0.05)  # settle after inventory sweep

    for epc_bytes in epc_filter_variants:
        for attempt in range(USER_MEM_RETRIES):
            try:
                result = reader.read_tag_mem(3, 0, USER_MEM_WORDS * 2, epc_bytes)
                if isinstance(result, (bytes, bytearray)):
                    return result.hex().upper()
                if isinstance(result, list):
                    return bytes(result).hex().upper()
            except Exception as ex:
                last_ex = ex
                print(f"           [WARN] attempt {attempt + 1}/{USER_MEM_RETRIES} "
                      f"(filter={epc_bytes[:4].hex()}...) failed: {ex}")
                if attempt < USER_MEM_RETRIES - 1:
                    time.sleep(USER_MEM_DELAY)

    print(f"           [WARN] USER mem read failed after all attempts: {last_ex}")
    return None


def build_event(event_type: str,
                epc: str,
                ts: datetime,
                user_memory: Optional[str] = None,
                rssi: Optional[int] = None,
                antenna_id: Optional[int] = None) -> dict:
    evt: dict = {
        "timestamp": ts.isoformat(timespec="milliseconds"),
        "eventType": event_type,
        "epc":       epc,
    }
    if user_memory is not None: evt["userMemory"] = user_memory
    if rssi        is not None: evt["rssi"]       = rssi
    if antenna_id  is not None: evt["antennaId"]  = antenna_id
    return evt


# ─────────────────────────────────────────────────────────────────────────────
#  SENDING
# ─────────────────────────────────────────────────────────────────────────────

def send_events_wifi(events: List[dict]) -> bool:
    """POST events to the server over WiFi."""
    try:
        response = requests.post(API_URL, json=events, timeout=API_TIMEOUT_SEC)
        response.raise_for_status()
        body = response.json()
        print(f"[WiFi ✓] {len(events)} event(s) sent → {body}")
        return True
    except requests.exceptions.ConnectionError:
        print("[WiFi ✗] No connection.")
    except requests.exceptions.Timeout:
        print(f"[WiFi ✗] Timed out after {API_TIMEOUT_SEC}s.")
    except requests.exceptions.HTTPError as ex:
        print(f"[WiFi ✗] HTTP {ex.response.status_code}: {ex.response.text[:200]}")
    except Exception as ex:
        print(f"[WiFi ✗] {ex}")
    return False


def send_events_lte(events: List[dict], pico_ser: serial.Serial) -> bool:
    """
    Send events to the Sixfab PicoLTE via serial.
    Protocol:
      Pi   → single JSON array terminated with \\n
      Pico → single JSON response line: {"success": true} or {"success": false, "error": "..."}
    """
    try:
        payload = json.dumps(events) + "\n"
        print(f"[LTE] Sending {len(events)} event(s) to Pico ({len(payload)} bytes)...")
        pico_ser.write(payload.encode('utf-8'))
        pico_ser.flush()

        response_line = pico_ser.readline().decode('utf-8').strip()
        if not response_line:
            print("[LTE ✗] No response from Pico — timed out.")
            return False

        result = json.loads(response_line)
        if result.get("success"):
            print("[LTE ✓] Events delivered via LTE.")
            return True
        else:
            print(f"[LTE ✗] Pico reported failure: {result.get('error', '?')}")
            return False

    except Exception as ex:
        print(f"[LTE ✗] Serial error: {ex}")
        return False


def send_with_fallback(events: List[dict],
                       pico_ser: Optional[serial.Serial]) -> bool:
    """
    Deliver events using WiFi first, LTE second.
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
    global _run
    reader:   Optional[mercury.Reader] = None
    pico_ser: Optional[serial.Serial]  = None

    try:
        # ── 1. Connect to RFID reader ─────────────────────────────────────────
        print(f"[INFO] Connecting to ThingMagic 6e Micro at {READER_URI} ...")
        reader = mercury.Reader(READER_URI, baudrate=READER_BAUDRATE)
        print("[INFO] Connected to RFID reader.")

        try:
            supported = reader.get_supported_regions()
            print(f"[INFO] Supported regions: {supported}")
            reader.set_region(REGION)
            print(f"[INFO] Region → {REGION}")
        except Exception as ex:
            print(f"[WARN] Region configuration skipped: {ex}")

        reader.set_read_plan([ANTENNA_PORT], "GEN2")
        print(f"[INFO] Read plan: antenna={ANTENNA_PORT}, GEN2")

        try:
            reader.set_read_powers([(ANTENNA_PORT, READ_POWER_CDBM)])
            print(f"[INFO] Read power: {READ_POWER_CDBM} cdBm ({READ_POWER_CDBM/100:.2f} dBm)")
        except Exception as ex:
            print(f"[WARN] Could not set read power: {ex}")

        # ── 2. Connect to PicoLTE ─────────────────────────────────────────────
        # Keep the port open for the lifetime of the program — avoids repeated
        # Pico resets that would occur if we opened/closed it per transmission.
        try:
            pico_ser = serial.Serial(PICO_PORT, PICO_BAUD, timeout=PICO_TIMEOUT_SEC)
            time.sleep(2)  # allow Pico to finish any boot reset
            print(f"[INFO] PicoLTE connected on {PICO_PORT}.")
        except Exception as ex:
            print(f"[WARN] Could not open PicoLTE on {PICO_PORT}: {ex}")
            print("[WARN] LTE fallback unavailable — WiFi only.")
            pico_ser = None

        print(f"\n[INFO] Window: {READ_WINDOW_SECS}s | "
              f"Tags: {len(ALLOWED_TAGS)} | "
              f"Force LTE: {FORCE_LTE} | "
              f"Require user memory: {REQUIRE_USER_MEMORY}")
        print("[INFO] Ctrl+C to stop.\n")

        # ── 3. Main collection loop ───────────────────────────────────────────
        while _run:
            window_start = time.time()
            # epc → {"ts", "rssi", "antenna", "user_mem", "user_mem_read"}
            unique_tags: Dict[str, dict] = {}

            print(f"[INFO] ── Window opened {datetime.now():%H:%M:%S} "
                  f"(collecting for {READ_WINDOW_SECS}s) ──")

            # ── 3a. Collect until window expires ──────────────────────────────
            while _run and (time.time() - window_start) < READ_WINDOW_SECS:
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

                    # First sighting of this EPC in this window
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

                    # Keep retrying user memory every cycle until it succeeds
                    if not unique_tags[epc]["user_mem_read"]:
                        user_hex = read_user_memory(reader, epc)
                        if user_hex:
                            unique_tags[epc]["user_mem"]      = user_hex
                            unique_tags[epc]["user_mem_read"] = True
                            print(f"           USER[0..{USER_MEM_WORDS-1}] = {user_hex}")

                time.sleep(0.05)

            # ── 3b. Build one event per unique EPC ────────────────────────────
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

            # ── 3c. Apply REQUIRE_USER_MEMORY filter ──────────────────────────
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

            # ── 3d. Send — WiFi first, LTE fallback ───────────────────────────
            send_with_fallback(filtered, pico_ser)
            print()

    except Exception as ex:
        print(f"\n[ERROR] Fatal: {ex}", file=sys.stderr)
        raise

    finally:
        print("[INFO] Cleaning up...")
        if reader:
            try: reader.destroy()
            except Exception: pass
        if pico_ser and pico_ser.is_open:
            try: pico_ser.close()
            except Exception: pass
        time.sleep(0.2)
        print("[INFO] Stopped.")


if __name__ == "__main__":
    main()