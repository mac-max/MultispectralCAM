import os
os.environ["BLINKA_FORCECHIP"] = "BCM2XXX"

import tkinter as tk
from tkinter import ttk
import board
import busio
import threading
import time
from adafruit_as7341 import AS7341, Gain

class SensorMonitor(tk.Toplevel):
    def __init__(self, master=None):
        super().__init__(master)
        self.title("AS7341 Live-Spektrum")
        self.geometry("400x580")
        self.running = True

        try:
            i2c = busio.I2C(board.SCL, board.SDA)
            self.sensor = AS7341(i2c)
            self.sensor.gain = Gain.GAIN_256X
        except Exception as e:
            ttk.Label(self, text=f"[Fehler beim Sensorinit: {e}]").pack()
            return

        self.build_ui()
        threading.Thread(target=self.update_loop, daemon=True).start()

    def build_ui(self):
        self.bars = {}

        frame = ttk.Frame(self)
        frame.pack(padx=20, pady=10)

        # Spektralkanäle
        self.channels = [
            ("415 nm", lambda: self.sensor.channel_415nm),
            ("445 nm", lambda: self.sensor.channel_445nm),
            ("480 nm", lambda: self.sensor.channel_480nm),
            ("515 nm", lambda: self.sensor.channel_515nm),
            ("555 nm", lambda: self.sensor.channel_555nm),
            ("590 nm", lambda: self.sensor.channel_590nm),
            ("630 nm", lambda: self.sensor.channel_630nm),
            ("680 nm", lambda: self.sensor.channel_680nm),
            ("NIR",    lambda: self.sensor.channel_nir),
            ("CLEAR",  lambda: self.sensor.channel_clear),
        ]

        for label_text, _ in self.channels:
            row = ttk.Frame(frame)
            row.pack(fill='x', pady=2)

            ttk.Label(row, text=label_text, width=8).pack(side='left')
            progress = ttk.Progressbar(row, orient='horizontal', length=250, mode='determinate', maximum=60000)
            progress.pack(side='left', padx=5)
            value_label = ttk.Label(row, text="0")
            value_label.pack(side='right')

            self.bars[label_text] = (progress, value_label)

        # LED-Steuerung
        self.light_on = False
        self.led_btn = ttk.Button(self, text="Licht EIN", command=self.toggle_light)
        self.led_btn.pack(pady=10)

        # Gain-Auswahl
        ttk.Label(self, text="Gain wählen:").pack()
        self.gain_options = {
            "0.5x": Gain.GAIN_0_5X,
            "1x": Gain.GAIN_1X,
            "4x": Gain.GAIN_4X,
            "16x": Gain.GAIN_16X,
            "64x": Gain.GAIN_64X,
            "128x": Gain.GAIN_128X,
            "256x": Gain.GAIN_256X
        }
        self.selected_gain = tk.StringVar(value="256x")
        gain_menu = ttk.OptionMenu(self, self.selected_gain, self.selected_gain.get(), *self.gain_options.keys(), command=self.set_gain)
        gain_menu.pack(pady=5)

    def toggle_light(self):
        self.light_on = not self.light_on
        self.sensor.led_current = 20
        self.sensor.led = self.light_on
        self.led_btn.config(text="Licht AUS" if self.light_on else "Licht EIN")

    def set_gain(self, label):
        try:
            self.sensor.gain = self.gain_options[label]
            print(f"[INFO] Gain gesetzt auf {label}")
        except Exception as e:
            print(f"[Fehler] Gain konnte nicht gesetzt werden: {e}")

    def update_loop(self):
        while self.running:
            try:
                for label_text, getter in self.channels:
                    value = getter()
                    self.bars[label_text][0]['value'] = value
                    self.bars[label_text][1]['text'] = str(value)
            except Exception as e:
                print("Fehler beim Sensorlesen:", e)
            time.sleep(0.5)

    def destroy(self):
        self.running = False
        super().destroy()
