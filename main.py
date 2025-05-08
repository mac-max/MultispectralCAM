import tkinter as tk
from tkinter import ttk
import board
import busio
from adafruit_pca9685 import PCA9685
from picamera2 import Picamera2
from PIL import Image, ImageTk
import threading
import time

# --- LED-Setup (PCA9685) ---
i2c = busio.I2C(board.SCL, board.SDA)
pca = PCA9685(i2c, address=0x41)
pca.frequency = 1000

channel_names = ["rot", "weiß", "blau", "grün", "orange", "gelb", "UV", "pink"]

def set_pwm(channel, percent):
    percent = max(0, min(100, percent))
    value = int((percent / 100) * 0xFFFF)
    pca.channels[channel].duty_cycle = value

# --- Kamera-Setup (picamera2) ---
picam2 = Picamera2()
picam2.configure(picam2.create_preview_configuration(main={"size": (640, 480)}))
picam2.start()

# --- GUI ---
root = tk.Tk()
root.title("Multispektralkamera Vorschau")

# Kamera-Frame
camera_label = ttk.Label(root)
camera_label.pack(padx=10, pady=10)

def update_camera():
    while True:
        frame = picam2.capture_array()
        img = Image.fromarray(frame)
        imgtk = ImageTk.PhotoImage(image=img)
        camera_label.imgtk = imgtk
        camera_label.configure(image=imgtk)
        time.sleep(0.05)

threading.Thread(target=update_camera, daemon=True).start()

# LED-Regler
led_frame = ttk.LabelFrame(root, text="LED Steuerung")
led_frame.pack(padx=10, pady=10, fill="x")

sliders = []

def on_slider_move(ch, var):
    val = var.get()
    set_pwm(ch, val)

for ch in range(len(channel_names)):
    row = ttk.Frame(led_frame)
    row.pack(fill="x", pady=2)
    ttk.Label(row, text=channel_names[ch], width=10).pack(side="left")
    var = tk.IntVar(value=0)
    slider = ttk.Scale(row, from_=0, to=100, orient="horizontal", variable=var,
                       command=lambda val, ch=ch, v=var: on_slider_move(ch, v))
    slider.pack(side="left", fill="x", expand=True, padx=5)
    sliders.append(var)

def all_off():
    for ch in range(8):
        sliders[ch].set(0)
        set_pwm(ch, 0)

ttk.Button(root, text="Alle LEDs aus", command=all_off).pack(pady=8)

root.mainloop()
