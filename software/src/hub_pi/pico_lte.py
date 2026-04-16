


def wait_for_pico_ready(ser: serial.Serial, timeout = PICO_WAIT_TIMEOUT) -> bool:
    """Wait for Pico to broadcast ready signal after LTE init."""
    print(f"[LTE] Waiting up to {timeout}s for Pico LTE ready signal...")
    deadline = time.time() + timeout
    while _run and time.time() < deadline:
        try:
            raw = ser.readline()
            if not raw:
                continue
            line = raw.decode('utf-8', errors='replace').strip()
            if not line:
                continue
            msg = json.loads(line)
            if msg.get("status") == "ready":
                print("[LTE] ✓ Pico is ready.")
                return True
        except (json.JSONDecodeError, Exception):
            pass
        
    if not _run:
        return False
    else:
        print("[LTE] ✗ Pico never became ready.")
        return False



def send_events_lte(events: List[dict], pico_ser: serial.Serial) -> bool:
    try:
        payload = json.dumps(events) + "\n"
        print(f"[LTE] Sending {len(events)} event(s) ({len(payload)} bytes)...")
        pico_ser.write(payload.encode('utf-8'))
        pico_ser.flush()

        deadline = time.time() + PICO_TIMEOUT_SEC
        while time.time() < deadline:
            raw = pico_ser.readline()
            if not raw:
                continue
            line = raw.decode('utf-8', errors='replace').strip()
            if not line:
                continue
            try:
                result = json.loads(line)
                if "success" in result:          # ignore status/ready messages
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