#!/usr/bin/env python3
"""
hub_sensors.py
Samples the hub-mounted AHTx0 (temperature + humidity) and PCF8591-connected
photodiode (brightness).

Brightness calibration:
  MIN_V and MAX_V should be tuned to the observed voltage range of your
  photodiode in complete darkness and brightest expected light respectively.

This module is intentionally HTTP-free — dispatch is handled by event_sender.
"""

from __future__ import annotations

from datetime import datetime

import board
import adafruit_ahtx0
import adafruit_pcf8591.pcf8591 as PCF
from adafruit_pcf8591.analog_in import AnalogIn

# ── Brightness calibration ────────────────────────────────────────────────────
MIN_V = 1.85   # voltage when photodiode is completely covered (dark floor)
MAX_V = 3.30   # voltage in brightest expected lighting condition

# ── Sensor initialisation ─────────────────────────────────────────────────────
_i2c         = None
_temp_sensor = None
_adc         = None
_light_ch    = None


def _init_sensors() -> None:
    """Lazily initialise I2C sensors on first use."""
    global _i2c, _temp_sensor, _adc, _light_ch
    if _i2c is not None:
        return
    _i2c         = board.I2C()
    _temp_sensor = adafruit_ahtx0.AHTx0(_i2c)
    _adc         = PCF.PCF8591(_i2c)
    _light_ch    = AnalogIn(_adc, 0)   # photodiode on channel C0


def _voltage_to_brightness(voltage: float) -> float:
    """
    Map photodiode voltage to a 0.0-100.0 brightness percentage.
    Higher voltage = less light (reverse-biased photodiode pulls voltage up
    in darkness). Clamps to the calibrated MIN_V / MAX_V range.
    """
    clamped = max(MIN_V, min(MAX_V, voltage))
    return round((1.0 - (clamped - MIN_V) / (MAX_V - MIN_V)) * 100.0, 1)


def sample_hub() -> dict:
    """
    Read all hub sensors and return a payload dict ready to POST.

    Returns:
        {
            "light":       float,  # brightness % (0-100)
            "humidity":    float,  # relative humidity %
            "temperature": float,  # deg C
            "timestamp":   str,    # ISO-8601 milliseconds
        }
    """
    _init_sensors()

    temperature = round(_temp_sensor.temperature, 2)
    humidity    = round(_temp_sensor.relative_humidity, 2)
    voltage     = _light_ch.voltage
    light       = _voltage_to_brightness(voltage)

    print(f"[HUB] temperature={temperature} C  "
          f"humidity={humidity} %  "
          f"light={light} %  (V={voltage:.3f})")

    return {
        "light":       light,
        "humidity":    humidity,
        "temperature": temperature,
        "timestamp":   datetime.now().isoformat(timespec="milliseconds"),
    }