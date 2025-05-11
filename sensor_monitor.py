import tkinter as tk
from tkinter import ttk
import board
import busio
from adafruit_as7341 import AS7341
from adafruit_bus_device.i2c_device import I2CDevice  # <--- direkter I2C-Zugriff
import threading
import time

class SensorMonitor(tk.Toplevel):
    def __init__(self, master=None):
        super().__init__(master)
        self.title("AS7341 Spektralsensor")
        self.geometry("420x600")

        try:
            i2c = busio.I2C(board.SCL, board.SDA)
            self.sensor = AS7341(i2c)
            self.device = I2CDevice(i2c, 0x39)  # <- direkter Zugriff auf das I2C-Gerät
        except Exception as e:
            ttk.Label(self, text=f"[Fehler beim Sensorinit: {e}]").pack()
            return

        self.light_on = False
        self.ir_filter_on = False
        self.running = True
        self.bars = {}

        self.build_ui()
        threading.Thread(target=self.update_loop, daemon=True).start()

    def build_ui(self):
        frame = ttk.Frame(self)
        frame.pack(padx=20, pady=10, fill="x")

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
            ttk.Label(row, text=label_text, width=8).pack(side='left')
            bar = ttk.Progressbar(row, orient='horizontal', length=250, mode='determinate', maximum=60000)
            bar.pack(side='left', padx=5)
            label = ttk.Label(row, text="0")
            label.pack(side='right')
            self.bars[label_text] = (bar, label)

        ttk.Label(self, text="Clear-Kanal").pack()
        self.clear_bar = ttk.Progressbar(self, orient='horizontal', length=250, mode='determinate', maximum=60000)
        self.clear_bar.pack(padx=10)
        self.clear_label = ttk.Label(self, text="0")
        self.clear_label.pack()

        self.flicker_label = ttk.Label(self, text="Flicker: wird erkannt ...", font=("Arial", 10, "bold"))
        self.flicker_label.pack(pady=10)

        self.led_btn = ttk.Button(self, text="Sensor-LED EIN", command=self.toggle_light)
        self.led_btn.pack(pady=5)

        self.ir_btn = ttk.Button(self, text="IR-Filter AKTIVIEREN", command=self.toggle_ir_filter)
        self.ir_btn.pack(pady=5)

    def toggle_light(self):
        self.light_on = not self.light_on
        self.sensor.led_current = 20
        self.sensor.led = self.light_on
        self.led_btn.config(text="Sensor-LED AUS" if self.light_on else "Sensor-LED EIN")

    def toggle_ir_filter(self):
        self.ir_filter_on = not self.ir_filter_on
        self.set_gpio_as_output(self.ir_filter_on)
        self.ir_btn.config(text="IR-Filter DEAKTIVIEREN" if self.ir_filter_on else "IR-Filter AKTIVIEREN")

    def set_gpio_as_output(self, high=True):
        try:
            value = 0b10 | (1 if high else 0)  # Bit 1 = Output, Bit 0 = Level
            with self.device as i2c:
                i2c.write(bytes([0x70, value]))
        except Exception as e:
            print(f"[Fehler] IR-Filter GPIO nicht gesetzt: {e}")

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
        self.set_gpio_as_output(False)  # IR-Filter beim Schließen deaktivieren
        super().destroy()
