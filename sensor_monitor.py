import os
os.environ["BLINKA_FORCECHIP"] = "BCM2XXX"

import tkinter as tk
from tkinter import ttk
import board
import busio
from adafruit_as7341 import AS7341, Gain

import threading
import time

# I2C & Sensor-Setup
i2c = busio.I2C(board.SCL, board.SDA)
sensor = AS7341(i2c)
sensor.gain = Gain.GAIN_256X  # Default-Gain

# GUI
root = tk.Tk()
root.title("AS7341 Live-Spektrum")

# Kanäle laut Datenblatt
channels = [
    ("415 nm", lambda: sensor.channel_415nm),
    ("445 nm", lambda: sensor.channel_445nm),
    ("480 nm", lambda: sensor.channel_480nm),
    ("515 nm", lambda: sensor.channel_515nm),
    ("555 nm", lambda: sensor.channel_555nm),
    ("590 nm", lambda: sensor.channel_590nm),
    ("630 nm", lambda: sensor.channel_630nm),
    ("680 nm", lambda: sensor.channel_680nm),
    ("NIR",    lambda: sensor.channel_nir),
    ("CLEAR",  lambda: sensor.channel_clear),
]

bars = {}

frame = ttk.Frame(root)
frame.pack(padx=20, pady=10)

# Balkenanzeigen für spektrale Kanäle
for label_text, _ in channels:
    row = ttk.Frame(frame)
    row.pack(fill='x', pady=2)

    label = ttk.Label(row, text=label_text, width=8)
    label.pack(side='left')

    progress = ttk.Progressbar(row, orient='horizontal', length=300, mode='determinate', maximum=60000)
    progress.pack(side='left', padx=5)

    value_label = ttk.Label(row, text="0")
    value_label.pack(side='right')

    bars[label_text] = (progress, value_label)

# Lichtquelle schalten
light_on = False
def toggle_light():
    global light_on
    light_on = not light_on
    sensor.led_current = 20
    sensor.led = light_on
    btn.config(text="Licht AUS" if light_on else "Licht EIN")

btn = ttk.Button(root, text="Licht EIN", command=toggle_light)
btn.pack(pady=10)

# Gain Dropdown
ttk.Label(root, text="Gain einstellen:").pack()
gain_options = {
    "0.5x": Gain.GAIN_0_5X,
    "1x": Gain.GAIN_1X,
    "4x": Gain.GAIN_4X,
    "16x": Gain.GAIN_16X,
    "64x": Gain.GAIN_64X,
    "128x": Gain.GAIN_128X,
    "256x": Gain.GAIN_256X
}
selected_gain = tk.StringVar(value="256x")

def set_gain(label):
    try:
        sensor.gain = gain_options[label]
        print(f"[INFO] Gain gesetzt auf {label}")
    except Exception as e:
        print(f"[Fehler] Gain konnte nicht gesetzt werden: {e}")

gain_menu = ttk.OptionMenu(root, selected_gain, selected_gain.get(), *gain_options.keys(), command=set_gain)
gain_menu.pack(pady=5)

# Live-Update in Hintergrundthread
def update_loop():
    while True:
        try:
            for label_text, getter in channels:
                value = getter()
                bars[label_text][0]['value'] = value
                bars[label_text][1]['text'] = str(value)
        except Exception as e:
            print("Fehler beim Sensor:", e)

        time.sleep(0.5)

threading.Thread(target=update_loop, daemon=True).start()

root.mainloop()
