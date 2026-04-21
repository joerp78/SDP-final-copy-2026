import time
import board
import busio
import adafruit_ahtx0

i2c = busio.I2C(board.SCL, board.SDA)
sensor = adafruit_ahtx0.AHTx0(i2c)

while True:
    print(f"Temperature: {sensor.temperature:.2f} C")
    print(f"Humidity: {sensor.relative_humidity:.2f} %")
    print("----------------------")
    time.sleep(2)