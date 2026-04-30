import time
import board
import busio
import adafruit_ahtx0
import qwiic_as7343

# Shared I2C bus for AHT temp/RH sensor
i2c = busio.I2C(board.SCL, board.SDA)
temp_sensor = adafruit_ahtx0.AHTx0(i2c)

# AS7343 spectral sensor
spectral_sensor = qwiic_as7343.QwiicAS7343()

if not spectral_sensor.is_connected():
    print("AS7343 not connected.")
    exit()

spectral_sensor.begin()
spectral_sensor.power_on()
spectral_sensor.spectral_measurement_enable()
spectral_sensor.set_auto_smux(spectral_sensor.kAutoSmux18Channels)

prev_brightness = None

print("Combined temp/humidity + AS7343 sensor reader running...")
print("Press Ctrl+C to stop.\n")

try:
    while True:
        # Temperature / humidity
        temperature_c = temp_sensor.temperature
        humidity = temp_sensor.relative_humidity

        # AS7343 readings
        spectral_sensor.read_all_spectral_data()

        blue = spectral_sensor.get_blue()
        green = spectral_sensor.get_green()
        red = spectral_sensor.get_red()
        nir = spectral_sensor.get_nir()

        brightness = red + green + blue
        estimated_lux = (0.2126 * red) + (0.7152 * green) + (0.0722 * blue)

        # Brightness label
        if brightness <= 5:
            brightness_label = "very dark"
        elif brightness <= 20:
            brightness_label = "dim"
        elif brightness <= 80:
            brightness_label = "normal brightness"
        elif brightness <= 300:
            brightness_label = "bright"
        else:
            brightness_label = "very bright"

        # Brightness change
        if prev_brightness is None:
            change_label = "starting measurement"
        else:
            change = brightness - prev_brightness
            if abs(change) < 2:
                change_label = "not really changing"
            elif change > 0:
                change_label = "getting brighter"
            else:
                change_label = "getting darker"

        prev_brightness = brightness

        # Color estimate
        if brightness == 0:
            color_label = "no visible color"
        elif abs(red - green) <= 2 and abs(green - blue) <= 2:
            color_label = "white / neutral"
        elif red > green and red > blue:
            color_label = "red / warm"
        elif green > red and green > blue:
            color_label = "green"
        elif blue > red and blue > green:
            color_label = "blue / cool"
        else:
            color_label = "mixed"

        # Spectrum type
        visible = brightness
        infrared = nir

        if visible <= 2 and infrared <= 2:
            spectrum_label = "very little light detected"
        elif infrared > visible:
            spectrum_label = "mostly infrared light"
        elif visible > infrared:
            spectrum_label = "mostly visible light"
        else:
            spectrum_label = "visible and infrared are similar"

        print("=" * 55)
        print(f"Temperature        : {temperature_c:.2f} °C")
        print(f"Relative Humidity  : {humidity:.2f} %")
        print(f"Brightness         : {brightness_label}")
        print(f"Brightness Change  : {change_label}")
        print(f"Estimated Color    : {color_label}")
        print(f"Light Spectrum     : {spectrum_label}")
        print(f"Estimated Lux      : {estimated_lux:.1f} lx")
        print(f"Raw RGB/NIR        : B={blue}, G={green}, R={red}, NIR={nir}")
        print("=" * 55)

        time.sleep(2)

except KeyboardInterrupt:
    print("\nStopped by user.")
