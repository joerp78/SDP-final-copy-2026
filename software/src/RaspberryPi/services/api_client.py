import config
import ujson
import time
from pico_lte.utils.status import Status
from pico_lte.common import debug


class APIClient:
    def __init__(self, pico_lte):

        self.pico_lte = pico_lte
        self.endpoint = config.API_ENDPOINT + "events"
    
    def send_events(self, events_list):
        """Send list of events to server using Sixfab HTTP"""
        try:
            print(f"Sending to: {self.endpoint}")
            
            # Convert events to JSON string
            json_data = ujson.dumps(events_list)

            self.pico_lte.http.set_server_url(self.endpoint)
      
            
            result = self.pico_lte.http.post(data=json_data)
            print(f"Response: {result}")
            
            # CHECK RETURN CODE
            http_code = None

            for item in result.get("response", []):
                if item.startswith("+QHTTPPOST:"):
                    parts = item.split(",")
                    if len(parts) >= 2:
                        http_code = int(parts[1].strip())
                        break

            if http_code and 200 <= http_code < 300:
                print(f"✓ Server accepted {len(events_list)} events (HTTP {http_code})")
                return True; 
            else:
                print(f"✗ Upload failed (HTTP {http_code})")
                return False; 
       
        except Exception as e:
            print(f"API Error: {e}")
            import sys
            sys.print_exception(e)  # Print full traceback
            return False
