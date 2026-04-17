#!/usr/bin/env python3
"""
tm6e.py
ThingMagic 6e Micro driver helpers: reader initialisation, EPC parsing,
user-memory reads, and event construction.
"""

import time
from datetime import datetime
from typing import Optional

import mercury

from config import (
    READER_URI,
    READER_BAUDRATE,
    REGION,
    ANTENNA_PORT,
    READ_POWER_CDBM,
    USER_MEM_WORDS,
    USER_MEM_RETRIES,
    USER_MEM_DELAY,
)


# ─────────────────────────────────────────────────────────────────────────────
#  CONNECT
# ─────────────────────────────────────────────────────────────────────────────

def connect_reader() -> mercury.Reader:
    """
    Open the ThingMagic 6e, configure region / read-plan / power,
    and return the ready-to-use Reader object.
    Raises on fatal failure so the caller can decide what to do.
    """
    print(f"[INFO] Connecting to ThingMagic 6e Micro at {READER_URI} ...")
    reader = mercury.Reader(READER_URI, baudrate=READER_BAUDRATE)
    print("[INFO] Connected to RFID reader.")

    # Region
    try:
        supported = reader.get_supported_regions()
        print(f"[INFO] Supported regions: {supported}")
        reader.set_region(REGION)
        print(f"[INFO] Region → {REGION}")
    except Exception as ex:
        print(f"[WARN] Region configuration skipped: {ex}")

    # Read plan
    reader.set_read_plan([ANTENNA_PORT], "GEN2")
    print(f"[INFO] Read plan: antenna={ANTENNA_PORT}, GEN2")

    # Power
    try:
        reader.set_read_powers([(ANTENNA_PORT, READ_POWER_CDBM)])
        print(f"[INFO] Read power: {READ_POWER_CDBM} cdBm "
              f"({READ_POWER_CDBM / 100:.2f} dBm)")
    except Exception as ex:
        print(f"[WARN] Could not set read power: {ex}")

    return reader


# ─────────────────────────────────────────────────────────────────────────────
#  EPC HELPERS
# ─────────────────────────────────────────────────────────────────────────────

_HEX_CHARS = set(b"0123456789ABCDEFabcdef")


def epc_to_str(epc) -> str:
    """Normalise any EPC representation to an upper-case hex string."""
    if isinstance(epc, (bytes, bytearray)):
        if epc and all(b in _HEX_CHARS for b in epc):
            return epc.decode("ascii").upper()
        return epc.hex().upper()
    return str(epc).replace(":", "").replace(" ", "").upper()


# ─────────────────────────────────────────────────────────────────────────────
#  USER MEMORY
# ─────────────────────────────────────────────────────────────────────────────

def read_user_memory(reader: mercury.Reader,
                     epc_hex: str) -> Optional[str]:
    """
    Read USER memory bank (bank 3) with an EPC filter.
    Tries the ASCII-encoded EPC first (Linux ThingMagic quirk),
    then falls back to raw binary.  Returns upper-case hex or None.
    """
    last_ex: Optional[Exception] = None
    epc_filter_variants = [
        epc_hex.encode("ascii"),        # b'0080B0443C...'
        bytes.fromhex(epc_hex),         # b'\x00\x80\xb0\x44...'
    ]

    time.sleep(0.05)                    # settle after inventory sweep

    for epc_bytes in epc_filter_variants:
        for attempt in range(USER_MEM_RETRIES):
            try:
                result = reader.read_tag_mem(
                    3, 0, USER_MEM_WORDS * 2, epc_bytes
                )
                if isinstance(result, (bytes, bytearray)):
                    return result.hex().upper()
                if isinstance(result, list):
                    return bytes(result).hex().upper()
            except Exception as ex:
                last_ex = ex
                print(
                    f"           [WARN] attempt {attempt + 1}/{USER_MEM_RETRIES} "
                    f"(filter={epc_bytes[:4].hex()}...) failed: {ex}"
                )
                if attempt < USER_MEM_RETRIES - 1:
                    time.sleep(USER_MEM_DELAY)

    print(f"           [WARN] USER mem read failed after all attempts: {last_ex}")
    return None


# ─────────────────────────────────────────────────────────────────────────────
#  EVENT BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def build_event(event_type: str,
                epc: str,
                ts: datetime,
                user_memory: Optional[str] = None,
                rssi: Optional[int] = None,
                antenna_id: Optional[int] = None) -> dict:
    """Construct a single event dict ready for JSON serialisation."""
    evt: dict = {
        "timestamp": ts.isoformat(timespec="milliseconds"),
        "eventType": event_type,
        "epc":       epc,
    }
    if user_memory is not None:
        evt["userMemory"] = user_memory
    if rssi is not None:
        evt["rssi"] = rssi
    if antenna_id is not None:
        evt["antennaId"] = antenna_id
    return evt