import tkinter as tk
from tkinter import ttk
import board
import busio
import re
from adafruit_pca9685 import PCA9685

class LEDController(tk.Toplevel):
    def __init__(self, master=None):
        super().__init__(master)
        self.title("LED PWM Steuerung – PCA9685 @ 0x40 & 0x41")
        self.geometry("460x800")

        # Namen pro PCA, bereits sortiert (aufsteigend)
        self.channel_1_names = [
            "644 nm", "3000 K", "455 nm", "510 nm", "610 nm", "597 nm", "434 nm", "pink"
        ]

        self.channel_2_names = [
            "453 nm", "441 nm", "421 nm", "391 nm", "378 nm", "495 nm", "591 nm",
            "630 nm", "655 nm", "863 nm", "968 nm", "pink", "519 nm", "5000 K"
        ]

        self.sliders_1 = []
        self.sliders_2 = []

        try:
            i2c = busio.I2C(board.SCL, board.SDA)
            self.pca_1 = PCA9685(i2c, address=0x40)
            self.pca_2 = PCA9685(i2c, address=0x58)
            self.pca_1.frequency = 1600
            self.pca_2.frequency = 1600
        except Exception as e:
            ttk.Label(self, text=f"[Fehler] I2C init: {e}").pack()
            return

        self.create_widgets()


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

    def create_widgets(self):
        # PCA 1 – sortieren
        sorted_channels_1 = sorted(
            [(i, name) for i, name in enumerate(self.channel_1_names)],
            key=lambda x: self.extract_wavelength(x[1])
        )

        ttk.Label(self, text="PCA9685 @ 0x40", font=('Arial', 12, 'bold')).pack(pady=(10, 0))
        for ch, name in sorted_channels_1:
            frame = ttk.Frame(self)
            frame.pack(fill='x', padx=10, pady=2)

            label = ttk.Label(frame, text=f"{name}", width=10)
            label.pack(side='left')

            var = tk.IntVar(value=0)
            slider = ttk.Scale(
                frame, from_=0, to=100, orient='horizontal',
                variable=var,
                command=lambda val, ch=ch, var=var: self.on_slider_move(self.pca_1, ch, var)
            )
            slider.pack(side='left', expand=True, fill='x', padx=(5, 5))

            self.sliders_1.append(var)

        # PCA 2 – sortieren (inkl. Offset!)
        sorted_channels_2 = sorted(
            [(i + 2, name) for i, name in enumerate(self.channel_2_names)],
            key=lambda x: self.extract_wavelength(x[1])
        )

        ttk.Label(self, text="PCA9685 @ 0x58", font=('Arial', 12, 'bold')).pack(pady=(20, 0))
        for ch, name in sorted_channels_2:
            frame = ttk.Frame(self)
            frame.pack(fill='x', padx=10, pady=2)

            label = ttk.Label(frame, text=f"{name}", width=10)
            label.pack(side='left')

            var = tk.IntVar(value=0)
            slider = ttk.Scale(
                frame, from_=0, to=100, orient='horizontal',
                variable=var,
                command=lambda val, ch=ch, var=var: self.on_slider_move(self.pca_2, ch, var)
            )
            slider.pack(side='left', expand=True, fill='x', padx=(5, 5))

            self.sliders_2.append(var)

        # Alles-aus-Button
        ttk.Button(self, text="Alle Kanäle AUS", command=self.all_off).pack(pady=20)

    def all_off(self):
        for ch, var in enumerate(self.sliders_1):
            var.set(0)
            self.set_pwm(self.pca_1, ch, 0)
        for ch, var in enumerate(self.sliders_2):
            var.set(0)
            self.set_pwm(self.pca_2, ch + 2, 0)
