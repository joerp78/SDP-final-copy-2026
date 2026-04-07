#!/usr/bin/env python3
"""
pico_serial_test.py
Standalone test to verify two-way serial communication with the PicoLTE.
Run this BEFORE rfid_reader.py to confirm the Pico is responding correctly.

Usage:
    python3 pico_serial_test.py
"""

import json
import time
import serial

PICO_PORT     = "/dev/ttyACM1"
PICO_BAUD     = 115200
TIMEOUT       = 30        # seconds to wait for each response

TEST_PAYLOAD = json.dumps([
    {
        "timestamp":  "2025-01-01T00:00:00.000",
        "eventType":  "ENTER",
        "epc":        "0080B0443C00000012787622",
        "userMemory": "0118000E00000000",
        "rssi":       -60,
        "antennaId":  1
    }
]) + "\n"


def read_lines_for(ser: serial.Serial, seconds: float):
    """Read and print all lines received within a time window."""
    deadline = time.time() + seconds
    lines = []
    while time.time() < deadline:
        raw = ser.readline()
        if raw:
            line = raw.decode('utf-8', errors='replace').strip()
            if line:
                print(f"  [PICO →] {line}")
                lines.append(line)
    return lines


def main():
    print(f"[TEST] Opening {PICO_PORT} at {PICO_BAUD} baud...")
    try:
        ser = serial.Serial(PICO_PORT, PICO_BAUD, timeout=1)
    except Exception as ex:
        print(f"[FAIL] Cannot open port: {ex}")
        return

    print("[TEST] Port opened. Waiting 5s for Pico to boot and print startup messages...\n")

    # ── Phase 1: Read everything the Pico prints during boot ─────────────────
    print("── Phase 1: Boot output ─────────────────────────────────────────────")
    boot_lines = read_lines_for(ser, 5)

    ready_seen = any(
        "ready" in l.lower() for l in boot_lines
    )
    print(f"\n  → {'✓ Ready signal seen' if ready_seen else '✗ No ready signal — Pico may still be booting or crashed'}")

    # ── Phase 2: Wait a bit longer if not ready yet ───────────────────────────
    if not ready_seen:
        print("\n[TEST] Waiting an additional 60s for LTE init...")
        more_lines = read_lines_for(ser, 60)
        boot_lines += more_lines
        ready_seen = any("ready" in l.lower() for l in boot_lines)
        print(f"  → {'✓ Ready signal seen' if ready_seen else '✗ Still no ready signal'}")

    # ── Phase 3: Send test payload ────────────────────────────────────────────
    print("\n── Phase 2: Sending test payload ────────────────────────────────────")
    print(f"  [PI →]   {TEST_PAYLOAD.strip()}")
    ser.write(TEST_PAYLOAD.encode('utf-8'))
    ser.flush()

    # ── Phase 4: Read response ────────────────────────────────────────────────
    print(f"\n── Phase 3: Waiting up to {TIMEOUT}s for response ───────────────────")
    deadline = time.time() + TIMEOUT
    response_received = False

    while time.time() < deadline:
        raw = ser.readline()
        if not raw:
            continue

        line = raw.decode('utf-8', errors='replace').strip()
        if not line:
            continue

        print(f"  [PICO →] {line}")

        try:
            result = json.loads(line)

            if isinstance(result, list):
                print("  → Echo detected (Pico REPL is active — main.py may not be running)")
                continue

            if isinstance(result, dict):
                if result.get("success"):
                    print("\n[PASS] ✓ Pico responded with success — LTE transmission worked!")
                else:
                    print(f"\n[FAIL] ✗ Pico reported failure: {result.get('error', '?')}")
                response_received = True
                break

        except json.JSONDecodeError:
            print(f"  → Non-JSON line (boot message or debug print)")

    if not response_received:
        print("\n[FAIL] ✗ No JSON response received within timeout.")
        print("        Possible causes:")
        print("        1. main.py is not running on the Pico")
        print("        2. LTE registration failed")
        print("        3. Pico crashed during processing")
        print("        4. Pico is still initializing — try increasing TIMEOUT")

    ser.close()
    print("\n[TEST] Done.")


if __name__ == "__main__":
    main()