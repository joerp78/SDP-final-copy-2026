import json

class JSONParser:
    @staticmethod
    def parse_rfid_reading(json_string):
        """Parse JSON from ThingMagic reader - returns list of events"""
        try:
            data = json.loads(json_string)
            
            # Handle both single object and array
            if isinstance(data, list):
                return [JSONParser._parse_single_event(event) for event in data]
            else:
                return [JSONParser._parse_single_event(data)]
                
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}")
    
    @staticmethod
    def _parse_single_event(event):
        """Parse a single RFID event"""
        return {
            'timestamp': event.get('timestamp'),
            'eventType': event.get('eventType'),
            'epc': event.get('epc'),
            'userMemory': event.get('userMemory'),
            'rssi': event.get('rssi'),
            'antennaId': event.get('antennaId')
        }