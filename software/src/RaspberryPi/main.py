from pico_lte.core import PicoLTE
from pico_lte.common import debug
import config
from data.json_parser import JSONParser
from services.api_client import APIClient
import time



def load_test_json():
    """Load JSON from test file"""
    try:
        with open(config.TEST_JSON_PATH, 'r') as f:
            return f.read()
    except Exception as e:
        print(f"Error loading test file: {e}")
        return None

def initialize_lte():
#     Initialize and connect to LTE network 
    print("=== Initializing Sixfab Pico LTE ===\n")
    
    # Create PicoLTE instance
    pico_lte = PicoLTE()
    
    pico_lte.network.register_network()
    pico_lte.http.set_context_id()
    pico_lte.network.get_pdp_ready()
    # Initialize modem
    print("Initializing modem...")
    if pico_lte.network.register_network():
        print("✓ Registered to network")
    else:
        print("✗ Failed to register to network")
        return None
        return pico_lte


def main():
    print("=== RFID Event Upload Test ===\n")

    pico_lte = initialize_lte()
    if not pico_lte:
        print("✗ LTE initialization failed")
        return
    

    api = APIClient(pico_lte)
    parser = JSONParser()
    
    if config.MOCK_USB_DATA:
        json_string = load_test_json()
        if not json_string:
            print("Failed to load test JSON file")
            return
        print(f"✓ Loaded JSON from: {config.TEST_JSON_PATH}")
            
        try:
            events = parser.parse_rfid_reading(json_string)
            print(f"✓ Parsed {len(events)} events\n")
                
            for i, event in enumerate(events, 1):
                print(f"  Event {i}: {event['eventType']} - {event['epc']}")
                
            success = api.send_events(events)
                
            if success:
                print(f"\n✓ Successfully uploaded {len(events)} events!")
            else:
                print(f"\n✗ Upload failed")
                
        except ValueError as e:
            print(f"✗ Parse error: {e}")
        except Exception as e:
            print(f"✗ Unexpected error: {e}")

    else:
        print("MOCK_USB_DATA is False - would read from USB here")


if __name__ == "__main__":
    main()