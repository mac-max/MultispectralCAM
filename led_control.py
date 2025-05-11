import tkinter as tk
from tkinter import ttk
import board
import busio
from adafruit_pca9685 import PCA9685

class LEDController(tk.Toplevel):
    def __init__(self, master=None):
        super().__init__(master)
        self.title("LED PWM Steuerung – PCA9685 @ 0x41")
        self.geometry("420x420")

        self.channel_names = ["rot", "weiß", "blau", "grün", "orange", "gelb", "UV", "pink"]
        self.sliders = []

        try:
            i2c = busio.I2C(board.SCL, board.SDA)
            self.pca = PCA9685(i2c, address=0x41)
            self.pca.frequency = 1000
        except Exception as e:
            ttk.Label(self, text=f"[Fehler] I2C init: {e}").pack()
            return

        self.create_widgets()

    def set_pwm(self, channel, percent):
        percent = max(0, min(100, percent))
        value = int((percent / 100) * 0xFFFF)
        self.pca.channels[channel].duty_cycle = value

    def on_slider_move(self, ch, var):
        val = var.get()
        self.set_pwm(ch, val)

    def create_widgets(self):
        for ch in range(len(self.channel_names)):
            frame = ttk.Frame(self)
            frame.pack(fill='x', padx=10, pady=4)

            label = ttk.Label(frame, text=f"Kanal {ch} ({self.channel_names[ch]})", width=18)
            label.pack(side='left')

            var = tk.IntVar(value=0)
            slider = ttk.Scale(frame, from_=0, to=100, orient='horizontal',
                               variable=var,
                               command=lambda val, ch=ch, var=var: self.on_slider_move(ch, var))
            slider.pack(side='left', expand=True, fill='x', padx=(5, 5))

            self.sliders.append(var)

        ttk.Button(self, text="Alle Kanäle AUS", command=self.all_off).pack(pady=12)

    def all_off(self):
        for ch in range(len(self.channel_names)):
            self.sliders[ch].set(0)
            self.set_pwm(ch, 0)
