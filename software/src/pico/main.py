import sys
import time
import ujson

DEBUG = True  #Set True only when connected via mpremote for debugging


def log(msg):
    if DEBUG:
        sys.stderr.write(msg + "\n")

def respond(success, error=None):
    if success:
        sys.stdout.write('{"success": true}\n')
    else:
        msg = str(error).replace('"', "'") if error else "Unknown error"
        sys.stdout.write('{"success": false, "error": "' + msg + '"}\n')


def initialize_lte():
    log("=== Initializing Sixfab Pico LTE ===")
    try:
        from pico_lte.core import PicoLTE
        pico_lte = PicoLTE()
    except Exception as e:
        log(f"✗ Failed to import or create PicoLTE: {e}")
        return None

    try:
        pico_lte.network.register_network()
        pico_lte.http.set_context_id()
        pico_lte.network.get_pdp_ready()
    except Exception as e:
        log(f"✗ Network setup failed: {e}")
        return None

    try:
        pico_lte.atcom.send_at_comm('AT+QHTTPCFG="sslctxid",1')
        pico_lte.atcom.send_at_comm('AT+QSSLCFG="sslversion",1,4')
        pico_lte.atcom.send_at_comm('AT+QSSLCFG="ciphersuite",1,0xFFFF')
        pico_lte.atcom.send_at_comm('AT+QSSLCFG="seclevel",1,0')
        pico_lte.atcom.send_at_comm('AT+QSSLCFG="sni",1,1')
        log("✓ SSL configured")
    except Exception as e:
        log(f"✗ SSL config failed: {e}")
        return None

    try:
        result = pico_lte.network.register_network()
        if result:
            log("✓ Registered to network")
            return pico_lte
        else:
            log("✗ register_network returned False")
            return None
    except Exception as e:
        log(f"✗ register_network failed: {e}")
        return None


def main():
    log("=== PicoLTE RFID Relay ===")

    try:
        from data.json_parser import JSONParser
        from services.api_client import APIClient
        imports_ok = True
    except Exception as e:
        log(f"✗ Import error: {e}")
        imports_ok = False

    pico_lte = initialize_lte()
    if not pico_lte:
        log("✗ LTE unavailable — will respond with errors.")

    if imports_ok and pico_lte:
        try:
            api    = APIClient(pico_lte)
            parser = JSONParser()
        except Exception as e:
            log(f"✗ Failed to create API/parser: {e}")
            api    = None
            parser = None
    else:
        api    = None
        parser = None

    log("✓ Ready. Broadcasting ready signal until first message...")

    import uselect
    poller = uselect.poll()
    poller.register(sys.stdin, uselect.POLLIN)

    first_line = None
    while True:
        sys.stdout.write('{"status": "ready"}\n')
        events = poller.poll(3000)
        if events:
            candidate = sys.stdin.readline()
            if candidate:
                stripped = candidate.strip()
                # Only break if it looks like real JSON payload
                if stripped.startswith('[') or stripped.startswith('{'):
                    try:
                        ujson.loads(stripped)  # validate it's actually parseable
                        first_line = candidate
                        break
                    except ValueError:
                        log(f"[WARN] Ignoring non-JSON input: {repr(stripped[:40])}")

    log("✓ Listening for JSON data on serial...")

    if first_line and first_line.strip():
        _handle_line(first_line, api, parser)

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
            log(f"[ERROR] {e}")
            respond(False, str(e))


def _handle_line(line, api, parser):
    line = line.replace('\r', '').replace('\n', '').strip()

    json_start = -1
    for i, ch in enumerate(line):
        if ch in ('[', '{'):
            json_start = i
            break

    if json_start == -1:
        log(f"[WARN] No JSON found in line: {repr(line[:80])}")
        respond(False, "No JSON found in received data")
        return

    if json_start > 0:
        log(f"[WARN] Stripped {json_start} garbage byte(s): {repr(line[:json_start])}")
        line = line[json_start:]

    log(f"[RX] {len(line)} byte(s)")
    log(f"[RX RAW] {repr(line[:80])}")

    if api is None or parser is None:
        respond(False, "LTE or parser not available")
        return

    try:
        data = ujson.loads(line)
        if isinstance(data, list):
            events = [_parse_event(e) for e in data]
        else:
            events = [_parse_event(data)]

        log(f"[INFO] Parsed {len(events)} event(s) — sending via LTE...")
        success = api.send_events(events)
        respond(success, None if success else "API call failed")

    except ValueError as e:
        log(f"[ERROR] JSON parse failed: {e}")
        respond(False, f"JSON parse failed: {e}")
    except Exception as e:
        log(f"[ERROR] {e}")
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
    log(f"[FATAL] {e}")
    while True:
        try:
            sys.stdin.readline()
            respond(False, f"Fatal crash: {e}")
        except Exception:
            time.sleep(1)
