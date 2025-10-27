import tkinter as tk
from tkinter import ttk
import board
import busio
import re
from adafruit_pca9685 import PCA9685

class LEDController:
    def __init__(self, use_gui=False, master=None):
        self.use_gui = use_gui
        self.master = master

        self.channel_1_names = [
            "644 nm", "3000 K", "455 nm", "510 nm", "610 nm", "597 nm", "434 nm", "pink"
        ]
        self.channel_2_names = [
            "453 nm", "441 nm", "421 nm", "391 nm", "378 nm", "495 nm", "591 nm",
            "630 nm", "655 nm", "863 nm", "968 nm", "pink", "519 nm", "5000 K"
        ]

        self.sorted_channels = []
        self.sliders = {}

        try:
            i2c = busio.I2C(board.SCL, board.SDA)
            self.pca_1 = PCA9685(i2c, address=0x40)
            self.pca_2 = PCA9685(i2c, address=0x58)
            self.pca_1.frequency = 1600
            self.pca_2.frequency = 1600
        except Exception as e:
            if self.use_gui:
                tk.Toplevel(self.master)
                ttk.Label(self.master, text=f"[Fehler] I2C init: {e}").pack()
            else:
                print(f"[Fehler] I2C init: {e}")
            return

        self.prepare_sorted_channels()

        if self.use_gui:
            self.window = tk.Toplevel(self.master)
            self.window.title("LED PWM Steuerung – PCA9685 @ 0x40 & 0x41")
            self.window.geometry("460x800")
            self.create_widgets()

    def get_all_channels(self):
        return [name for _, name in self.sorted_channels]

    def set_channel_by_name(self, name, percent):
        for (pca, ch), ch_name in self.sorted_channels:
            if ch_name == name:
                self.set_pwm(pca, ch, percent)
                if name in self.sliders:
                    self.sliders[name].set(percent)
                return
        print(f"[WARN] Kanalname '{name}' nicht gefunden.")

    def get_channel_value(self, name):
        for (pca, ch), ch_name in self.sorted_channels:
            if ch_name == name:
                raw_value = pca.channels[ch].duty_cycle
                return round(raw_value / 0xFFFF * 100, 1)
        print(f"[WARN] Kanalname '{name}' nicht gefunden.")
        return None

    def set_pwm(self, pca, channel, percent):
        percent = max(0, min(100, percent))
        value = int((percent / 100) * 0xFFFF)
        pca.channels[channel].duty_cycle = value

    def on_slider_move(self, pca, ch, var):
        val = var.get()
        self.set_pwm(pca, ch, val)

    def extract_wavelength(self, label):
        match = re.search(r"(\d+)", label)
        return int(match.group(1)) if match else float('inf')

    def prepare_sorted_channels(self):
        sorted_1 = sorted(
            [(self.pca_1, i, name) for i, name in enumerate(self.channel_1_names)],
            key=lambda x: self.extract_wavelength(x[2])
        )
        sorted_2 = sorted(
            [(self.pca_2, i + 2, name) for i, name in enumerate(self.channel_2_names)],
            key=lambda x: self.extract_wavelength(x[2])
        )
        self.sorted_channels = [((pca, ch), name) for (pca, ch, name) in sorted_1 + sorted_2]

    def create_widgets(self):
        for (pca, ch), name in self.sorted_channels:
            frame = ttk.Frame(self.window)
            frame.pack(fill='x', padx=10, pady=2)

            label = ttk.Label(frame, text=f"{name}", width=10)
            label.pack(side='left')

            var = tk.IntVar(value=0)
            slider = ttk.Scale(
                frame, from_=0, to=100, orient='horizontal',
                variable=var,
                command=lambda val, pca=pca, ch=ch, var=var: self.on_slider_move(pca, ch, var)
            )
            slider.pack(side='left', expand=True, fill='x', padx=(5, 5))

            self.sliders[name] = var

        ttk.Button(self.window, text="Alle Kanäle AUS", command=self.all_off).pack(pady=20)

    def all_off(self):
        for (pca, ch), name in self.sorted_channels:
            if name in self.sliders:
                self.sliders[name].set(0)
            self.set_pwm(pca, ch, 0)
