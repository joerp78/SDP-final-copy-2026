#!/usr/bin/env python3
"""
wifi.py
Sends event payloads to the server over HTTP (WiFi/Ethernet).
"""

from typing import List

import requests

from config import API_URL, API_TIMEOUT_SEC


def send_events_wifi(events: List[dict]) -> bool:
    """POST *events* as JSON to the API endpoint."""
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