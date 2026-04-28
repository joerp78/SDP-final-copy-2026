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

def compute_conductivity(cond_word: int) -> float:
    """
    Decode the packed conductivity word and convert it to a conductivity percent.

    Tag encoding:
      - bit 15: feedback_low_enabled
      - bits 11:0: raw peak-to-peak amplitude in 12-bit ADC counts

    Conversion rules provided by the firmware team:
      - raw pk-pk < 10 mV -> 0.0%
      - if feedback_low_enabled == 1:
          10 mV  -> 65.0%
          2000 mV -> 100.0%
      - if feedback_low_enabled == 0:
          10 mV  -> 0.0%
          2500 mV -> 64.0%

    For now, the raw 12-bit amplitude is converted to millivolts assuming a
    3.0 V ADC full scale because battery processing is not yet available on the
    reader side.

    Returns:
        Conductivity percentage rounded to 1 decimal place.
    """
    feedback_low_enabled = (cond_word & 0x8000) != 0
    amplitude_raw = cond_word & 0x0FFF

    amplitude_mv = (amplitude_raw * 3000.0) / 4095.0

    if amplitude_mv < 10.0:
        return 0.0

    if feedback_low_enabled:
        if amplitude_mv >= 2000.0:
            return 100.0
        percent = 65.0 + ((amplitude_mv - 10.0) * (100.0 - 65.0) / (2000.0 - 10.0))
        return round(percent, 1)

    if amplitude_mv >= 2500.0:
        return 64.0

    percent = (amplitude_mv - 10.0) * 64.0 / (2500.0 - 10.0)
    return round(percent, 1)


def compute_moisture(phase_word: int) -> float:
    """
    Decode the packed phase word and convert it to a moisture percent.

    Tag encoding:
      - bit 15: phase_delay_valid
      - bits 11:0: signed phase delay in deg_x10 (12-bit two's complement)

    Conversion rules provided by the firmware team:
      - phase_delay_valid == 0 -> -1.0%
      - phase > 30 deg  -> 100.0%
      - phase < -170 deg -> 0.0%
      - linearly interpolate in between

    Returns:
        Moisture percentage rounded to 1 decimal place, or -1.0 when invalid.
    """
    phase_delay_valid = (phase_word & 0x8000) != 0
    if not phase_delay_valid:
        return -1.0

    phase_raw_12 = phase_word & 0x0FFF
    if phase_raw_12 & 0x0800:
        phase_raw_12 -= 0x1000

    phase_deg = phase_raw_12 / 10.0

    if phase_deg >= 30.0:
        return 100.0
    if phase_deg <= -170.0:
        return 0.0

    percent = (phase_deg - (-170.0)) * 100.0 / (30.0 - (-170.0))
    return round(percent, 1)


def decode_plant(user_hex: str, epc: str, ts: datetime) -> Optional[Tuple[int, dict]]:
    """
    Decode a 4-word plant sensor blob from user memory.

    Word layout:
      [0] temperature  (raw ADC count)
      [1] phase packet (bit15 valid, bits11:0 signed deg_x10)
      [2] conductivity packet (bit15 feedback_low_enabled, bits11:0 raw amplitude)
      [3] battery      (uint16 -> mV)

    Plant ID is looked up from EPC_PLANT_MAP.
    Returns (plant_id, payload dict) or None on failure.
    """
    raw = bytes.fromhex(user_hex)
    if len(raw) < 8:
        print(f"[WARN] EPC {epc}: user memory too short ({len(raw)} bytes, need 8).")
        return None

    temp_raw, phase_raw, cond_raw, batt_raw = struct.unpack(">HHHH", raw[:8])

    plant_id = EPC_PLANT_MAP.get(epc)
    if plant_id is None:
        print(f"[WARN] EPC {epc}: not found in EPC_PLANT_MAP - skipped.")
        return None

    # Temperature is still passed through with the legacy raw*0.01 scaling used
    # elsewhere in the hub path. Phase and conductivity now come from packed
    # firmware words and are converted into percentages by the helpers above.
    conductivity_pct = compute_conductivity(cond_raw)
    moisture_pct = compute_moisture(phase_raw)

    return plant_id, {
        "plantId":          plant_id,
        "name":             "",          # managed server-side via POST /api/plants
        "temperature":      round(temp_raw  * 0.01, 2),
        "soilConductivity": conductivity_pct,
        "soilMoisture":     moisture_pct,
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
