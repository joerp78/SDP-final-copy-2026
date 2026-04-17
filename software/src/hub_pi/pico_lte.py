#!/usr/bin/env python3
"""
pico_lte.py
Manages the Sixfab PicoLTE serial link: opening the port, waiting for the
Pico's "ready" handshake, and transmitting JSON event payloads over LTE.
"""

import json
import time
from threading import Event
from typing import List, Optional

import serial

from config import (
    PICO_PORT,
    PICO_BAUD,
    PICO_TIMEOUT_SEC,
    PICO_WAIT_TIMEOUT,
)


# ─────────────────────────────────────────────────────────────────────────────
#  CONNECT
# ─────────────────────────────────────────────────────────────────────────────

def open_pico_serial(shutdown: Event) -> Optional[serial.Serial]:
    """
    Open the PicoLTE serial port and wait for the ready handshake.
    Returns a live serial.Serial on success, or None on failure.
    """
    try:
        ser = serial.Serial(PICO_PORT, PICO_BAUD, timeout=PICO_TIMEOUT_SEC)
        if not wait_for_pico_ready(ser, shutdown):
            print("[WARN] Pico not ready — LTE unavailable.")
            ser.close()
            return None
        return ser
    except Exception as ex:
        print(f"[WARN] Could not open PicoLTE on {PICO_PORT}: {ex}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
#  HANDSHAKE
# ─────────────────────────────────────────────────────────────────────────────

def wait_for_pico_ready(ser: serial.Serial,
                        shutdown: Event,
                        timeout: int = PICO_WAIT_TIMEOUT) -> bool:
    """
    Block until the Pico broadcasts {"status": "ready"} or *timeout* expires.
    Respects the *shutdown* event so the program can exit cleanly.
    """
    print(f"[LTE] Waiting up to {timeout}s for Pico LTE ready signal...")
    deadline = time.time() + timeout

    while not shutdown.is_set() and time.time() < deadline:
        try:
            raw = ser.readline()
            if not raw:
                continue
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            msg = json.loads(line)
            if msg.get("status") == "ready":
                print("[LTE] ✓ Pico is ready.")
                return True
        except (json.JSONDecodeError, Exception):
            pass

    if shutdown.is_set():
        return False

    print("[LTE] ✗ Pico never became ready.")
    return False


# ─────────────────────────────────────────────────────────────────────────────
#  SEND
# ─────────────────────────────────────────────────────────────────────────────

def send_events_lte(events: List[dict],
                    pico_ser: serial.Serial) -> bool:
    """
    Serialize *events* as JSON, push them over the serial link,
    then block until the Pico replies with a success / failure JSON object.
    """
    try:
        payload = json.dumps(events) + "\n"
        print(f"[LTE] Sending {len(events)} event(s) ({len(payload)} bytes)...")
        pico_ser.write(payload.encode("utf-8"))
        pico_ser.flush()

        deadline = time.time() + PICO_TIMEOUT_SEC
        while time.time() < deadline:
            raw = pico_ser.readline()
            if not raw:
                continue
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                result = json.loads(line)
                if "success" in result:
                    if result["success"]:
                        print("[LTE ✓] Events delivered.")
                        return True
                    else:
                        print(f"[LTE ✗] Pico failure: {result.get('error', '?')}")
                        return False
            except json.JSONDecodeError:
                continue

        print("[LTE ✗] Timed out waiting for response.")
        return False

    except Exception as ex:
        print(f"[LTE ✗] Serial error: {ex}")
        return False