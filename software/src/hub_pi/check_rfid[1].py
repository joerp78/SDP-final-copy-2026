#!/usr/bin/env python3
"""
rfid_reader_debug.py
Stripped-down debug version — no tag filtering, no user memory reads,
prints every cycle so you can see exactly what the reader is doing.
"""

import signal
import sys
import time
from datetime import datetime
from typing import Optional

import mercury

# ── CONFIG ────────────────────────────────────────────────────────────────────
READER_URI      = "tmr:///dev/ttyACM0"
READER_BAUDRATE = 115200
REGION          = "NA2"
ANTENNA_PORT    = 1
READ_POWER_CDBM = 2500
READ_WINDOW_MS  = 500

_run = True

def _on_signal(sig, frame):
    global _run
    print("\n[INFO] Stopping...")
    _run = False

signal.signal(signal.SIGINT,  _on_signal)
signal.signal(signal.SIGTERM, _on_signal)


def epc_to_str(epc) -> str:
    if isinstance(epc, (bytes, bytearray)):
        return epc.hex().upper()
    return str(epc).replace(":", "").replace(" ", "").upper()


def main():
    reader: Optional[mercury.Reader] = None
    cycle = 0

    try:
        print(f"[INFO] Connecting to {READER_URI} ...")
        reader = mercury.Reader(READER_URI, baudrate=READER_BAUDRATE)
        print("[INFO] Connected.")

        reader.set_region(REGION)
        print(f"[INFO] Region → {REGION}")

        reader.set_read_plan([ANTENNA_PORT], "GEN2")
        print(f"[INFO] Read plan set: antenna={ANTENNA_PORT}, GEN2")

        try:
            reader.set_read_powers([(ANTENNA_PORT, READ_POWER_CDBM)])
            print(f"[INFO] Power → {READ_POWER_CDBM} cdBm")
        except Exception as ex:
            print(f"[WARN] Could not set power: {ex}")

        print("\n[INFO] Starting read loop — Ctrl+C to stop\n")

        while _run:
            cycle += 1
            now = datetime.now()

            # ── Heartbeat so you can see the loop is alive ────────────────────
            print(f"[CYCLE {cycle:04d}] {now:%H:%M:%S.%f} — reading for {READ_WINDOW_MS}ms...")

            try:
                tags_now = reader.read(READ_WINDOW_MS)
            except Exception as ex:
                print(f"  [WARN] Read error: {ex}")
                tags_now = []

            if not tags_now:
                print(f"  → No tags detected this cycle.")
            else:
                # ── Print EVERY tag, no filtering ─────────────────────────────
                print(f"  → {len(tags_now)} tag(s) detected:")
                for tag in tags_now:
                    epc    = epc_to_str(tag.epc)
                    rssi   = getattr(tag, "rssi",    "N/A")
                    ant    = getattr(tag, "antenna", "N/A")
                    count  = getattr(tag, "read_count", "N/A")
                    print(f"     EPC:{epc}  RSSI:{rssi}  ANT:{ant}  COUNT:{count}")

            time.sleep(0.05)

    except Exception as ex:
        print(f"\n[ERROR] {ex}", file=sys.stderr)
        raise

    finally:
        if reader:
            try:
                reader.destroy()
            except Exception:
                pass
        print("[INFO] Done.")


if __name__ == "__main__":
    main()