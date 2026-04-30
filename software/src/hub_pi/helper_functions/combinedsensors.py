import time
import board
import busio
import adafruit_ahtx0
import qwiic_as7343

# Temp / humidity sensor
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

CHANNEL_LABELS = [
    ("FZ",   "~405 nm", "near UV / violet"),
    ("FY",   "~425 nm", "violet / blue"),
    ("FXL",  "~450 nm", "blue"),
    ("NIR",  "~855 nm", "near infrared"),
    ("VIS1", "~475 nm", "blue-green"),
    ("VIS2", "~515 nm", "cyan / green"),
    ("VIS3", "~550 nm", "green"),
    ("VIS4", "~590 nm", "yellow"),
    ("VIS5", "~630 nm", "orange"),
    ("VIS6", "~680 nm", "red"),
    ("VIS7", "~730 nm", "deep red"),
    ("VIS8", "~760 nm", "far red"),
]

prev_brightness = None

print("Combined temp/humidity + AS7343 reader running...")
print("Press Ctrl+C to stop.\n")

try:
    while True:
        # Temp / humidity
        temperature_c = temp_sensor.temperature
        humidity = temp_sensor.relative_humidity

        # Spectral sensor
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

        # Estimated color
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
        if brightness <= 2 and nir <= 2:
            spectrum_label = "very little light detected"
        elif nir > brightness:
            spectrum_label = "mostly infrared light"
        elif brightness > nir:
            spectrum_label = "mostly visible light"
        else:
            spectrum_label = "visible and infrared are similar"

        # Wavelength/raw data
        wavelength_data = []

        for i, (channel, wavelength, color_name) in enumerate(CHANNEL_LABELS):
            raw_value = spectral_sensor.get_data(i)
            wavelength_data.append((channel, wavelength, color_name, raw_value))

        dominant_channel = max(wavelength_data, key=lambda x: x[3])

        # Output
        print("=" * 65)
        print(f"Temperature          : {temperature_c:.2f} °C")
        print(f"Relative Humidity    : {humidity:.2f} %")
        print(f"Brightness           : {brightness_label}")
        print(f"Brightness Change    : {change_label}")
        print(f"Estimated Color      : {color_label}")
        print(f"Light Spectrum       : {spectrum_label}")
        print(f"Estimated Lux        : {estimated_lux:.1f} lx")
        print(f"Dominant Wavelength  : {dominant_channel[1]} ({dominant_channel[2]})")
        print(f"Raw RGB/NIR          : B={blue}, G={green}, R={red}, NIR={nir}")

        print("\nWavelength Data:")
        print(f"{'Channel':<7} {'Wavelength':<10} {'Color':<20} {'Raw Count'}")
        print("-" * 55)

        for channel, wavelength, color_name, raw_value in wavelength_data:
            print(f"{channel:<7} {wavelength:<10} {color_name:<20} {raw_value}")

        print("=" * 65 + "\n")

        time.sleep(2)

except KeyboardInterrupt:
    print("\nStopped by user.")