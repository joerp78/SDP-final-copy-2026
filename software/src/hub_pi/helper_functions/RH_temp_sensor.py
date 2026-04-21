import time
import board
import busio
import adafruit_ahtx0
from smbus2 import SMBus

# Shared I2C bus
i2c = busio.I2C(board.SCL, board.SDA)

# RH / temperature sensor
temp_sensor = adafruit_ahtx0.AHTx0(i2c)

# PCF8591 ADC for photodiode
ADC_ADDR = 0x48
adc_bus = SMBus(1)

def read_light_raw():
    # PCF8591 needs one dummy read before the real one
    adc_bus.read_byte(ADC_ADDR)
    return adc_bus.read_byte(ADC_ADDR)

try:
    while True:
        temperature_c = temp_sensor.temperature
        humidity = temp_sensor.relative_humidity
        light_raw = read_light_raw()

        print(f"Temperature: {temperature_c:.2f} C")
        print(f"Humidity: {humidity:.2f} %")
        print(f"Light (raw): {light_raw}")
        print("----------------------")

        time.sleep(2)

except KeyboardInterrupt:
    print("\nStopped by user.")