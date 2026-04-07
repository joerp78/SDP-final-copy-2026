import sys
import time
import ujson                       # MicroPython's native JSON — avoids JSONDecodeError issue


def respond(success, error=None):
    if success:
        sys.stdout.write('{"success": true}\n')
    else:
        msg = str(error).replace('"', "'") if error else "Unknown error"
        sys.stdout.write('{"success": false, "error": "' + msg + '"}\n')
    # No flush() — MicroPython stdout is unbuffered


def initialize_lte():
    print("=== Initializing Sixfab Pico LTE ===")
    try:
        from pico_lte.core import PicoLTE
        pico_lte = PicoLTE()
    except Exception as e:
        print(f"✗ Failed to import or create PicoLTE: {e}")
        return None

    try:
        pico_lte.network.register_network()
    except Exception as e:
        print(f"✗ register_network (1) failed: {e}")

    try:
        pico_lte.http.set_context_id()
    except Exception as e:
        print(f"✗ set_context_id failed: {e}")

    try:
        pico_lte.network.get_pdp_ready()
    except Exception as e:
        print(f"✗ get_pdp_ready failed: {e}")

    try:
        result = pico_lte.network.register_network()
        if result:
            print("✓ Registered to network")
            return pico_lte
        else:
            print("✗ register_network (2) returned False")
            return None
    except Exception as e:
        print(f"✗ register_network (2) failed: {e}")
        return None


def main():
    print("=== PicoLTE RFID Relay ===")

    try:
        from data.json_parser import JSONParser
        from services.api_client import APIClient
        imports_ok = True
    except Exception as e:
        print(f"✗ Import error: {e}")
        imports_ok = False

    pico_lte = initialize_lte()
    if not pico_lte:
        print("✗ LTE unavailable — will respond with errors.")

    if imports_ok and pico_lte:
        try:
            api    = APIClient(pico_lte)
            parser = JSONParser()
        except Exception as e:
            print(f"✗ Failed to create API/parser: {e}")
            api    = None
            parser = None
    else:
        api    = None
        parser = None

    print("✓ Ready. Broadcasting ready signal until first message...")

    # ── Broadcast ready using uselect for non-blocking stdin reads ────────────
    import uselect
    poller = uselect.poll()
    poller.register(sys.stdin, uselect.POLLIN)

    first_line = None
    while True:
        sys.stdout.write('{"status": "ready"}\n')
        # Poll for incoming data — 3 second timeout (milliseconds)
        events = poller.poll(3000)
        if events:
            first_line = sys.stdin.readline()
            if first_line and first_line.strip():
                break   # got real data — exit ready loop

    print("✓ Listening for JSON data on serial...")

    # Process the first line that broke us out of the ready loop
    if first_line and first_line.strip():
        _handle_line(first_line, api, parser)

    # ── Main listen loop ──────────────────────────────────────────────────────
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                time.sleep(0.1)
                continue
            line = line.strip()
            if not line:
                continue
            _handle_line(line, api, parser)
        except Exception as e:
            print(f"[ERROR] {e}")
            respond(False, str(e))


def _handle_line(line, api, parser):
    """Process one received line — shared by ready loop and main loop."""
    line = line.replace('\r', '').replace('\n', '').strip()

    # ── Strip any garbage prepended by MicroPython REPL echo ─────────────────
    # Find the first JSON character — either '[' for an array or '{' for an object
    json_start = -1
    for i, ch in enumerate(line):
        if ch in ('[', '{'):
            json_start = i
            break

    if json_start == -1:
        print(f"[WARN] No JSON found in line: {repr(line[:80])}")
        respond(False, "No JSON found in received data")
        return

    if json_start > 0:
        print(f"[WARN] Stripped {json_start} garbage byte(s): {repr(line[:json_start])}")
        line = line[json_start:]

    print(f"[RX] {len(line)} byte(s)")
    print(f"[RX RAW] {repr(line[:80])}")

    if api is None or parser is None:
        respond(False, "LTE or parser not available")
        return

    try:
        data = ujson.loads(line)
        if isinstance(data, list):
            events = [_parse_event(e) for e in data]
        else:
            events = [_parse_event(data)]

        print(f"[INFO] Parsed {len(events)} event(s) — sending via LTE...")
        success = api.send_events(events)
        respond(success, None if success else "API call failed")

    except ValueError as e:
        print(f"[ERROR] JSON parse failed: {e}")
        respond(False, f"JSON parse failed: {e}")
    except Exception as e:
        print(f"[ERROR] {e}")
        respond(False, str(e))


def _parse_event(event):
    return {
        'timestamp':  event.get('timestamp'),
        'eventType':  event.get('eventType'),
        'epc':        event.get('epc'),
        'userMemory': event.get('userMemory'),
        'rssi':       event.get('rssi'),
        'antennaId':  event.get('antennaId'),
    }


try:
    main()
except Exception as e:
    print(f"[FATAL] {e}")
    while True:
        try:
            sys.stdin.readline()
            respond(False, f"Fatal crash: {e}")
        except Exception:
            time.sleep(1)