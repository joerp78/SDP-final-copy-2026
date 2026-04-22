#!/usr/bin/env python3
"""
config.py
Central configuration for the RFID + LTE gateway project.
Every tunable lives here so the four runtime modules stay focused on logic.
"""

# ─── ThingMagic 6e Micro (RFID) ──────────────────────────────────────────────
READER_URI       = "tmr:///dev/ttyACM0"
READER_BAUDRATE  = 115200
REGION           = "NA2"
ANTENNA_PORT     = 1
READ_POWER_CDBM  = 2500               # centidBm  → 25.00 dBm
READ_WINDOW_MS   = 500                # ms per blocking mercury.read() call
READ_WINDOW_SECS = 5                  # total collection window in seconds
USER_MEM_WORDS   = 4
USER_MEM_RETRIES = 8
USER_MEM_DELAY   = 0.15               # seconds between retry attempts

# ─── API / Server ────────────────────────────────────────────────────────────
API_URL          = "https://joepaola.com/sdp"
API_TIMEOUT_SEC  = 10

# ─── Behaviour flags ─────────────────────────────────────────────────────────
REQUIRE_USER_MEMORY = True             # suppress events that lack user memory
FORCE_LTE           = False             # True → skip WiFi, always use LTE
TEST_DATA           = True              #True, use test data

# ─── LTE / Sixfab PicoLTE ────────────────────────────────────────────────────
PICO_PORT         = "/dev/ttyACM1"
PICO_BAUD         = 115200
PICO_TIMEOUT_SEC  = 60                 # response timeout per transmission
PICO_WAIT_TIMEOUT = 60                 # how long to wait for "ready" at boot

# ─── Tag allow-list ──────────────────────────────────────────────────────────
ALLOWED_TAGS = {
    "0080B0443C00000012787622", #GEN 1 Board
    "0080B0443C00000012787627", #GEN 1 Board
    "0080B0443C000000129D9CAA" #GEN 2 Board
}

EPC_PLANT_MAP: dict[str, int] = {
    "0080B0443C000000129D9CAA": 1,
    # "0080B0443C000000129D9CBB": 2,   # add more tags here
}