import time
import board
import adafruit_ahtx0
import adafruit_pcf8591.pcf8591 as PCF
from adafruit_pcf8591.analog_in import AnalogIn

i2c = board.I2C()

temp_sensor = adafruit_ahtx0.AHTx0(i2c)

adc = PCF.PCF8591(i2c)
light_channel = AnalogIn(adc, 0)

try:
    while True:
        temperature_c = temp_sensor.temperature
        humidity = temp_sensor.relative_humidity
        raw = light_channel.value
        voltage = light_channel.voltage

        # Normalize to 0.0-1.0 based on observed min/max voltage range
        # With 1MΩ resistor and 3.3V supply:
        MIN_V = 0.0
        MAX_V = 3.3
        normalized = (voltage - MIN_V) / (MAX_V - MIN_V)

        # Flip if needed — change to (1 - normalized) if behavior is backwards
        brightness_pct = round((1-normalized) * 100, 1)

        print(f"Temperature: {temperature_c:.2f} C")
        print(f"Humidity:    {humidity:.2f} %")
        print(f"Voltage:     {voltage:.3f} V")
        print(f"Brightness:  {brightness_pct}%")
        print("----------------------")

        time.sleep(2)

except KeyboardInterrupt:
    print("\nStopped by user.")