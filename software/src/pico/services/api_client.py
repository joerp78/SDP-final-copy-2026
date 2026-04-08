import config
import ujson
import time
from pico_lte.utils.status import Status

class APIClient:
    def __init__(self, pico_lte):
        self.pico_lte = pico_lte
        self.endpoint = config.API_ENDPOINT

    def send_events(self, events_list):
        print(f"[LTE] Sending {len(events_list)} event(s) in chunks of 1")
        all_success = True

        for i, event in enumerate(events_list):
            chunk = [event]
            json_data = ujson.dumps(chunk)
            print(f"[LTE] Event {i+1}/{len(events_list)} — {len(json_data)} bytes")

            try:
                self.pico_lte.http.set_content_type(4)
                self.pico_lte.http.set_context_id(1)
                self.pico_lte.http.set_server_url(self.endpoint)

                result = self.pico_lte.http.post(data=json_data, input_timeout=15, timeout=60)
                print(f"[LTE] POST result: {result}")

                success = False
                for item in result.get("response", []):
                    if item.startswith("+QHTTPPOST:"):
                        parts = item.split(",")
                        if len(parts) >= 2:
                            http_code = int(parts[1].strip())
                            if 200 <= http_code < 300:
                                print(f"[LTE ✓] Event {i+1} accepted (HTTP {http_code})")
                                success = True
                            else:
                                print(f"[LTE ✗] Event {i+1} rejected (HTTP {http_code})")
                        break

                if not success and result.get("status") == 0:
                    print(f"[LTE ✓] Event {i+1} succeeded")
                    success = True

                if not success:
                    print(f"[LTE ✗] Event {i+1} failed")
                    all_success = False

            except Exception as e:
                print(f"[LTE ✗] Event {i+1} error: {e}")
                all_success = False

            # Small delay between posts to let the modem reset the HTTP session
            time.sleep(2)

        return all_success
