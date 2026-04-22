#!/usr/bin/env python3
"""
event_sender.py
Transforms raw RFID tag data into the JSON payloads expected by the BLOSSM
server and dispatches them to the correct API endpoints over WiFi (with
optional LTE fallback via PicoLTE).

Endpoint targets (from ApiController.java):
  POST /api/plants/{id}/readings  - list of Plant { plantId, name, temperature,
                                                    soilMoisture, soilConductivity,
                                                    battery, timestamp }
  POST /api/hub/readings          - list of Hub   { light, humidity, temperature,
                                                    timestamp }

User-memory layout (each word = 2 bytes, big-endian, all uint16):
  Word 0 - temperature      (deg C,  uint16 x 0.01)
  Word 1 - conductivity     (uS/cm,  uint16 x 0.01)
  Word 2 - moisture         (%,      uint16 x 0.01)
  Word 3 - battery          (mV,     uint16)

Plant ID is resolved from the tag EPC via EPC_PLANT_MAP in config.py.
"""

from __future__ import annotations

import struct
from datetime import datetime
from typing import List, Optional, Tuple

import requests
import serial

from config import API_URL, API_TIMEOUT_SEC, FORCE_LTE, EPC_PLANT_MAP
from hub_sensors import sample_hub


# -----------------------------------------------------------------------------
#  USER-MEMORY DECODER
# -----------------------------------------------------------------------------

def decode_plant(user_hex: str, epc: str, ts: datetime) -> Optional[Tuple[int, dict]]:
    """
    Decode a 4-word plant sensor blob from user memory.

    Word layout:
      [0] temperature  (uint16 x 0.01 -> deg C)
      [1] conductivity (uint16 x 0.01 -> uS/cm)
      [2] moisture     (uint16 x 0.01 -> %)
      [3] battery      (uint16        -> mV)

    Plant ID is looked up from EPC_PLANT_MAP.
    Returns (plant_id, payload dict) or None on failure.
    """
    raw = bytes.fromhex(user_hex)
    if len(raw) < 8:
        print(f"[WARN] EPC {epc}: user memory too short ({len(raw)} bytes, need 8).")
        return None

    temp_raw, cond_raw, moist_raw, batt_raw = struct.unpack(">HHHH", raw[:8])

    plant_id = EPC_PLANT_MAP.get(epc)
    if plant_id is None:
        print(f"[WARN] EPC {epc}: not found in EPC_PLANT_MAP - skipped.")
        return None

    return plant_id, {
        "plantId":          plant_id,
        "name":             "",          # managed server-side via POST /api/plants
        "temperature":      round(temp_raw  * 0.01, 2),
        "soilConductivity": round(cond_raw  * 0.01, 2),
        "soilMoisture":     round(moist_raw * 0.01, 2),
        "battery":          batt_raw,    # raw mV, no scaling
        "timestamp":        ts.replace(tzinfo=None).isoformat(timespec="milliseconds"),
    }


# -----------------------------------------------------------------------------
#  HTTP HELPERS
# -----------------------------------------------------------------------------

def _post(url: str, payload: list, label: str) -> bool:
    """POST payload as JSON to url. Always prints the server response."""
    try:
        resp = requests.post(url, json=payload, timeout=API_TIMEOUT_SEC)
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        print(f"[Server response] HTTP {resp.status_code} -> {body}")
        resp.raise_for_status()
        print(f"[WiFi OK] {label}")
        return True
    except requests.exceptions.ConnectionError:
        print(f"[WiFi FAIL] {label}: no connection.")
    except requests.exceptions.Timeout:
        print(f"[WiFi FAIL] {label}: timed out after {API_TIMEOUT_SEC}s.")
    except requests.exceptions.HTTPError:
        print(f"[WiFi FAIL] {label}: request failed (see server response above).")
    except Exception as ex:
        print(f"[WiFi FAIL] {label}: {ex}")
    return False


def _base_url() -> str:
    """
    Preserve any path prefix in API_URL so subpath-hosted servers work.
    e.g. API_URL = 'https://joepaola.com/sdp'
    yields endpoints like 'https://joepaola.com/sdp/api/plants/1/readings'.
    """
    return API_URL.rstrip("/")


def _send_lte(payload: list, pico_ser: serial.Serial, label: str) -> bool:
    try:
        from pico_lte import send_events_lte
        ok = send_events_lte(payload, pico_ser)
        print(f"[LTE {'OK' if ok else 'FAIL'}] {label}")
        return ok
    except Exception as ex:
        print(f"[LTE FAIL] {label}: {ex}")
        return False


def _dispatch(url: str,
              payload: list,
              label: str,
              pico_ser: Optional[serial.Serial]) -> bool:
    """WiFi-first, LTE-fallback dispatch (respects FORCE_LTE flag)."""
    if not FORCE_LTE:
        if _post(url, payload, label):
            return True
        print(f"[INFO] WiFi failed for {label} - falling back to LTE.")
    else:
        print(f"[INFO] FORCE_LTE=True - skipping WiFi for {label}.")

    if pico_ser is None or not pico_ser.is_open:
        print(f"[WARN] Pico serial unavailable - cannot send {label} via LTE.")
        return False

    return _send_lte(payload, pico_ser, label)


# -----------------------------------------------------------------------------
#  PUBLIC ENTRY POINTS
# -----------------------------------------------------------------------------

def send_hub_reading(pico_ser: Optional[serial.Serial] = None) -> bool:
    """
    Sample hub sensors and POST the reading to POST /api/hub/readings.
    Reuses the shared _dispatch helper for WiFi/LTE fallback.

    Args:
        pico_ser: open serial.Serial to PicoLTE, or None if unavailable.

    Returns:
        True if the reading was sent successfully, False otherwise.
    """
    try:
        reading = sample_hub()
    except Exception as ex:
        print(f"[ERROR] Hub sensor read failed: {ex}")
        return False

    url   = f"{_base_url()}/api/hub/readings"
    label = "hub reading -> POST /api/hub/readings"
    return _dispatch(url, [reading], label, pico_ser)


def send_rfid_events(
    events: List[dict],
    pico_ser: Optional[serial.Serial] = None,
) -> None:
    """
    Decode each RFID event's userMemory and POST the resulting plant readings
    to the server, grouped by plant ID.
    """
    base = _base_url()
    plant_readings: dict[int, List[dict]] = {}  # plant_id -> [reading, ...]

    for evt in events:
        epc      = evt.get("epc", "?")
        ts_str   = evt.get("timestamp", datetime.now().isoformat())
        ts       = datetime.fromisoformat(ts_str)
        user_hex = evt.get("userMemory")

        if not user_hex:
            print(f"[INFO] EPC {epc}: no user memory - skipped.")
            continue

        result = decode_plant(user_hex, epc, ts)
        if not result:
            continue

        plant_id, payload = result
        plant_readings.setdefault(plant_id, []).append(payload)
        print(f"[INFO] EPC {epc} -> plant {plant_id} | "
              f"temp={payload['temperature']} C  "
              f"conductivity={payload['soilConductivity']} uS/cm  "
              f"moisture={payload['soilMoisture']} %  "
              f"battery={payload['battery']} mV")

    if not plant_readings:
        print("[INFO] No decodable readings to send.")
        return

    for plant_id, readings in plant_readings.items():
        url   = f"{base}/api/plants/{plant_id}/readings"
        label = (f"{len(readings)} reading(s) for plant {plant_id} "
                 f"-> POST /api/plants/{plant_id}/readings")
        _dispatch(url, readings, label, pico_ser)