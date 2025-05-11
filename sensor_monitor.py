import tkinter as tk
from tkinter import ttk
import board
import busio
from adafruit_as7341 import AS7341
import threading
import time

class SensorMonitor(tk.Toplevel):
    def __init__(self, master=None):
        super().__init__(master)
        self.title("AS7341 Spektralsensor")
        self.geometry("400x550")

        # Sensor initialisieren
        try:
            i2c = busio.I2C(board.SCL, board.SDA)
            self.sensor = AS7341(i2c)
        except Exception as e:
            ttk.Label(self, text=f"[Fehler beim Sensorinit: {e}]").pack()
            return

        self.light_on = False
        self.running = True

        self.bars = {}
        self.build_ui()

        self.thread = threading.Thread(target=self.update_loop, daemon=True)
        self.thread.start()

    def build_ui(self):
        frame = ttk.Frame(self)
        frame.pack(padx=20, pady=10, fill="x")

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
            ("NIR",    lambda: self.sensor.nir_channel),
        ]

        for label_text, _ in self.channels:
            row = ttk.Frame(frame)
            row.pack(fill='x', pady=2)

            label = ttk.Label(row, text=label_text, width=8)
            label.pack(side='left')

            progress = ttk.Progressbar(row, orient='horizontal', length=250, mode='determinate', maximum=60000)
            progress.pack(side='left', padx=5)

            value_label = ttk.Label(row, text="0")
            value_label.pack(side='right')

            self.bars[label_text] = (progress, value_label)

        # Clear-Kanal
        ttk.Label(self, text="Clear-Kanal").pack()
        self.clear_bar = ttk.Progressbar(self, orient='horizontal', length=250, mode='determinate', maximum=60000)
        self.clear_bar.pack(padx=10)
        self.clear_label = ttk.Label(self, text="0")
        self.clear_label.pack()

        # Flicker
        self.flicker_label = ttk.Label(self, text="Flicker: wird erkannt ...", font=("Arial", 10, "bold"))
        self.flicker_label.pack(pady=10)

        # Licht-Button
        self.led_btn = ttk.Button(self, text="Sensor-LED EIN", command=self.toggle_light)
        self.led_btn.pack(pady=5)

    def toggle_light(self):
        self.light_on = not self.light_on
        self.sensor.led_current = 20
        self.sensor.led = self.light_on
        self.led_btn.config(text="Sensor-LED AUS" if self.light_on else "Sensor-LED EIN")

    def flicker_text(self, code):
        return {
            0: "Kein Flimmern erkannt",
            1: "50 Hz erkannt",
            2: "60 Hz erkannt",
            3: "100 Hz erkannt",
            4: "120 Hz erkannt",
            255: "Fehler / keine Messung"
        }.get(code, f"Unbekannt ({code})")

    def update_loop(self):
        while self.running:
            try:
                for label_text, getter in self.channels:
                    value = getter()
                    self.bars[label_text][0]['value'] = value
                    self.bars[label_text][1]['text'] = str(value)

                c = self.sensor.clear_channel
                self.clear_bar['value'] = c
                self.clear_label['text'] = str(c)

                f = self.sensor.flicker_detected
                self.flicker_label['text'] = "Flicker: " + self.flicker_text(f)

            except Exception as e:
                print("Fehler beim Sensorlesen:", e)

            time.sleep(0.5)

    def destroy(self):
        self.running = False
        super().destroy()
