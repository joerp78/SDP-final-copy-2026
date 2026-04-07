#!/usr/bin/env python3
"""
rfid_reader.py
Raspberry Pi 3B + ThingMagic 6e Micro (USB)

Detects ENTER/LEAVE events for a known set of EPC tags and POSTs
each event batch to: https://joepaola.com/sdp/api/events

Requirements:
    pip3 install mercuryapi requests

Hardware:
    ThingMagic 6e Micro → USB → Raspberry Pi 3B
    Device typically appears as /dev/ttyUSB0
    Confirm with: ls /dev/ttyUSB*

Permissions:
    sudo usermod -a -G dialout $USER    (then log out and back in)
    OR run with: sudo python3 rfid_reader.py  (for quick testing only)
"""

import signal
import sys
import time
from datetime import datetime
from threading import Lock
from typing import Dict, List, Optional

import mercury
import requests


# ─────────────────────────────────────────────────────────────────────────────
#  CONFIGURATION — edit these to match your setup
# ─────────────────────────────────────────────────────────────────────────────

READER_URI       = "tmr:///dev/ttyACM0"   # USB device path on Pi
READER_BAUDRATE  = 115200                  # Baud rate for USB-serial negotiation
REGION           = "NA2"                   # Regulatory region ("NA2" = North America)
ANTENNA_PORT     = 1                       # Antenna port on the 6e Micro
READ_POWER_CDBM  = 2500                    # Read power in centi-dBm (= 25.00 dBm)
READ_WINDOW_MS   = 500                     # Milliseconds per blocking read cycle
PRESENCE_TIMEOUT = 5.0                     # Seconds of no reads before LEAVE fires
USER_MEM_WORDS   = 4                       # 16-bit words to read from USER bank
USER_MEM_RETRIES = 8                       # Retry attempts for USER memory reads
USER_MEM_DELAY   = 0.15                    # Seconds between USER memory retries

API_URL          = "https://joepaola.com/sdp/api/events"
API_TIMEOUT_SEC  = 10                      # HTTP request timeout in seconds
REQUIRE_USER_MEMORY = True

# Only these EPCs will trigger ENTER/LEAVE events (case-insensitive comparison below)
ALLOWED_TAGS = {
    "0080B0443C00000012787622",
    "0080B0443C00000012787627",
}


# ─────────────────────────────────────────────────────────────────────────────
#  GLOBALS
# ─────────────────────────────────────────────────────────────────────────────

_run: bool = True
_tag_lock: Lock = Lock()

# Tracks per-EPC presence state
# epc -> {"present": bool, "last_seen": datetime}
_tag_states: Dict[str, dict] = {}


# ─────────────────────────────────────────────────────────────────────────────
#  SIGNAL HANDLING — graceful Ctrl+C / SIGTERM shutdown
# ─────────────────────────────────────────────────────────────────────────────

def _on_signal(sig, frame) -> None:
    global _run
    print("\n[INFO] Shutdown signal received — stopping after current cycle...")
    _run = False

signal.signal(signal.SIGINT,  _on_signal)
signal.signal(signal.SIGTERM, _on_signal)


# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────
_HEX_CHARS = set(b'0123456789ABCDEFabcdef')

def epc_to_str(epc) -> str:
    """
    Normalise an EPC value into an uppercase hex string.
    The mercury library may return bytes, bytearray, or a colon-separated string
    depending on firmware version — this handles all cases.
    """
    if isinstance(epc, (bytes, bytearray)):
        if epc and all(b in _HEX_CHARS for b in epc):
            return epc.decode('ascii').upper()
            # Otherwise it's raw binary — convert normally
        return epc.hex().upper()
    return str(epc).replace(":", "").replace(" ", "").upper()


def read_user_memory(reader: mercury.Reader, epc_hex: str) -> Optional[str]:
    """
    Read USER memory bank using read_tag_mem with an EPC filter.
    bank=3 (USER), address=0, count=USER_MEM_WORDS*2 bytes.
    EPC filter passed as ASCII hex bytes to match the Linux ThingMagic
    encoding behaviour discovered during EPC normalisation.
    """
    last_ex: Optional[Exception] = None

    # Try ASCII hex encoding first (matches Linux ThingMagic EPC encoding),
    # fall back to raw binary on failure
    epc_filter_variants = [
        epc_hex.encode('ascii'),    # b'0080B0443C00000012787622' — try first
        bytes.fromhex(epc_hex),     # b'\x00\x80\xb0\x44...'     — fallback
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
    """
    Build a camelCase dict that maps to the Java RFIDEvent model.

    Resulting JSON structure example:
    {
        "timestamp":  "2025-06-10T14:23:01.456",
        "eventType":  "ENTER",
        "epc":        "0080B0443C00000012787622",
        "userMemory": "AABB00112233CCDD",
        "rssi":       -52,
        "antennaId":  1
    }
    """
    evt: dict = {
        "timestamp": ts.isoformat(timespec="milliseconds"),  # ISO 8601, ms precision
        "eventType": event_type,                              # "ENTER" | "LEAVE"
        "epc":       epc,
    }
    # Only include optional fields when they have values (mirrors C# nullable props)
    if user_memory is not None:
        evt["userMemory"] = user_memory
    if rssi is not None:
        evt["rssi"] = rssi
    if antenna_id is not None:
        evt["antennaId"] = antenna_id
    return evt


def send_events(events: List[dict]) -> bool:
    """
    POST a list of event dicts to the Spring Boot API endpoint.
    The controller expects: @RequestBody List<RFIDEvent>

    On HTTP 2xx the server returns:
        {"success": true, "count": N, "ids": [...]}
    """
    if not events:
        return True

    try:
        response = requests.post(
            API_URL,
            json=events,               # auto-encodes list as JSON array
            timeout=API_TIMEOUT_SEC
        )
        response.raise_for_status()    # raises on 4xx/5xx
        body = response.json()
        print(f"[API ✓] {len(events)} event(s) sent → {body}")
        return True

    except requests.exceptions.HTTPError as ex:
        # Server returned a 4xx or 5xx response
        print(f"[API ✗] HTTP {ex.response.status_code}: "
              f"{ex.response.text[:300]}")
    except requests.exceptions.ConnectionError:
        print("[API ✗] Cannot reach server — check network connectivity.")
    except requests.exceptions.Timeout:
        print(f"[API ✗] Request timed out after {API_TIMEOUT_SEC}s.")
    except Exception as ex:
        print(f"[API ✗] Unexpected error: {ex}")

    return False


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    global _run
    reader: Optional[mercury.Reader] = None

    try:
        # ── 1. Connect to reader ──────────────────────────────────────────────
        print(f"[INFO] Connecting to ThingMagic 6e Micro at {READER_URI} ...")
        # mercury.Reader() handles connection internally during construction
        reader = mercury.Reader(READER_URI, baudrate=READER_BAUDRATE)
        print("[INFO] Connected to RFID reader.")

        # ── 2. Set regulatory region ──────────────────────────────────────────
        try:
            supported = reader.get_supported_regions()
            print(f"[INFO] Supported regions: {supported}")
            reader.set_region(REGION)
            print(f"[INFO] Region → {REGION}")
        except Exception as ex:
            # Non-fatal: reader may already have a valid region programmed
            print(f"[WARN] Region configuration skipped: {ex}")

        # ── 3. Read plan: single antenna, GEN2 ───────────────────────────────
        reader.set_read_plan([ANTENNA_PORT], "GEN2")
        print(f"[INFO] Read plan: antenna={ANTENNA_PORT}, protocol=GEN2")

        # ── 4. RF read power ──────────────────────────────────────────────────
        try:
            reader.set_read_powers([(ANTENNA_PORT, READ_POWER_CDBM)])
            print(f"[INFO] Read power: {READ_POWER_CDBM} centi-dBm "
                  f"({READ_POWER_CDBM / 100:.2f} dBm)")
        except Exception as ex:
            print(f"[WARN] Could not set read power ({ex}) — using reader default.")

        print(f"\n[INFO] Watching {len(ALLOWED_TAGS)} allowed tag(s). "
              f"Ctrl+C to stop.\n")

        # ── 5. Main polling loop ──────────────────────────────────────────────
        while _run:
            now = datetime.now()
            events_to_send: List[dict] = []

            # ── 5a. Blocking read (READ_WINDOW_MS) ────────────────────────────
            try:
                tags_now = reader.read(READ_WINDOW_MS)
            except Exception as ex:
                print(f"[WARN] Read error: {ex}")
                tags_now = []

            with _tag_lock:
                tag_data_map: dict = {}

                # ── 5b. ENTER detection ───────────────────────────────────────
                for tag in tags_now:
                    epc = epc_to_str(tag.epc)

                    if epc not in ALLOWED_TAGS:
                        continue  # ignore unknown tags

                    # Initialise state dict on first ever sight of this tag
                    if epc not in _tag_states:
                        _tag_states[epc] = {"present": False, "last_seen": now, "user_mem_read": False}

                    state = _tag_states[epc]
                    state["last_seen"] = now   # refresh heartbeat
                    tag_data_map[epc] = tag

                    if not state["present"]:
                        # ── Tag just entered the field ────────────────────────
                        state["present"] = True

                        rssi     = getattr(tag, "rssi",    None)
                        antenna  = getattr(tag, "antenna", None)

                        print(f"{now:%H:%M:%S}  [ENTER]  EPC:{epc}  "
                              f"RSSI:{rssi}  ANT:{antenna}")

                        # Read USER memory once on first detection (with retries)
                        user_hex = read_user_memory(reader, epc)
                        if user_hex:
                            print(f"           USER[0..{USER_MEM_WORDS - 1}] = {user_hex}")

                        events_to_send.append(
                            build_event("ENTER", epc, now,
                                        user_memory=user_hex,
                                        rssi=rssi,
                                        antenna_id=antenna)
                        )

                # ── 5c. LEAVE detection (presence timeout) ────────────────────
                for epc, state in _tag_states.items():
                    if state["present"]:
                        elapsed = (now - state["last_seen"]).total_seconds()
                        if elapsed > PRESENCE_TIMEOUT:
                            state["present"]       = False
                            state["user_mem_read"] = False
                            print(f"{now:%H:%M:%S}  [LEAVE]  EPC:{epc}")
                            events_to_send.append(
                                build_event("LEAVE", epc, now)
                            )

            # ── 5d. Retry USER memory for present tags not yet read ────────
                for epc, state in _tag_states.items():
                    if state["present"] and not state["user_mem_read"] and epc in tag_data_map:
                        print(f"{now:%H:%M:%S}  [MEM RETRY]  EPC:{epc}")
                        user_hex = read_user_memory(reader, epc)
                        if user_hex:
                            state["user_mem_read"] = True
                            print(f"           USER[0..{USER_MEM_WORDS - 1}] = {user_hex}")

            # ── 5e. POST the batch to the API (outside the lock) ──────────────
            if events_to_send:
                if REQUIRE_USER_MEMORY:
                    filtered = [
                        e for e in events_to_send
                        if e["eventType"] == "LEAVE" or e.get("userMemory") is not None
                    ]
                else:
                    filtered = events_to_send

                if filtered:
                    send_events(filtered)
                else:
                    print(f"[INFO] {len(events_to_send)} event(s) suppressed — no user memory read yet.")

            time.sleep(0.05)  # yield CPU between cycles

    except Exception as ex:
        print(f"\n[ERROR] Fatal: {ex}", file=sys.stderr)
        raise

    finally:
        print("[INFO] Cleaning up...")
        if reader is not None:
            try:
                reader.destroy()
                print("[INFO] Reader connection closed.")
            except Exception:
                pass
        time.sleep(0.2)
        print("[INFO] Stopped. Goodbye.")


if __name__ == "__main__":
    main()