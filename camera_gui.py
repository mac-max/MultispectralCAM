import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
from led_control import LEDController
# from led_control_widget import LEDControlWidget
from camera_settings import CameraSettings
from sensor_monitor import SensorMonitor

import subprocess
import threading
import cv2
import numpy as np


class CameraStream:
    def __init__(self, width=640, height=480, framerate=15, shutter=None, gain=None):
        self.width = width
        self.height = height
        self.framerate = framerate
        self.shutter = shutter
        self.gain = gain

        self.buffer = b""
        self.frame = None
        self.running = False
        self.proc = None
        self.thread = None

        self.start()

    def build_command(self):
        cmd = [
            "libcamera-vid",
            "--nopreview",
            "-t", "0",
            "--width", str(self.width),
            "--height", str(self.height),
            "--framerate", str(self.framerate),
            "--codec", "mjpeg",
            "--inline",
            "-o", "-"
        ]
        if self.shutter:
            cmd += ["--shutter", str(self.shutter)]
        if self.gain:
            cmd += ["--gain", str(self.gain)]
        return cmd

    def start(self):
        self.running = True
        self.proc = subprocess.Popen(
            self.build_command(),
            stdout=subprocess.PIPE,
            bufsize=10 ** 8
        )
        self.thread = threading.Thread(target=self._read_stream, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.proc:
            self.proc.terminate()
        if self.thread:
            self.thread.join(timeout=1)

    def reconfigure(self, **kwargs):
        self.stop()
        self.width = kwargs.get("width", self.width)
        self.height = kwargs.get("height", self.height)
        self.framerate = kwargs.get("framerate", self.framerate)
        self.shutter = kwargs.get("shutter", self.shutter)
        self.gain = kwargs.get("gain", self.gain)
        self.buffer = b""
        self.frame = None
        self.start()

    def _read_stream(self):
        while self.running:
            try:
                data = self.proc.stdout.read(4096)
                if not data:
                    break
                self.buffer += data

                start = self.buffer.find(b'\xff\xd8')
                end = self.buffer.find(b'\xff\xd9')
                if start != -1 and end != -1 and end > start:
                    jpg = self.buffer[start:end + 2]
                    self.buffer = self.buffer[end + 2:]
                    img = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                    if img is not None:
                        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                        self.frame = Image.fromarray(img)
            except Exception as e:
                print("Fehler im Kamera-Thread:", e)

    def get_frame(self):
        return self.frame





# GUI-Setup
root = tk.Tk()
root.title("Multispektralkamera Vorschau")

# Kameraanzeige
camera_label = ttk.Label(root)
camera_label.pack(padx=10, pady=10)

stream = CameraStream()


def update_gui():
    frame = stream.get_frame()
    if frame:
        imgtk = ImageTk.PhotoImage(image=frame)
        camera_label.imgtk = imgtk
        camera_label.configure(image=imgtk)
    root.after(50, update_gui)


update_gui()


# # LED-Fenster öffnen
# def open_led_window(root):
#     try:
#         LEDController(root)
#     except Exception as e:
#         print("[ERROR] LED-Controller konnte nicht geöffnet werden:", e)


ttk.Button(root, text="LED Steuerung öffnen", command=lambda: LEDController(root)).pack(pady=10)
ttk.Button(root, text="Kameraeinstellungen", command=lambda: CameraSettings(root, stream)).pack(pady=5)
ttk.Button(root, text="Spektralsensor anzeigen", command=lambda: SensorMonitor(root)).pack(pady=5)


# Sauberes Beenden
def on_close():
    stream.stop()
    root.destroy()


root.protocol("WM_DELETE_WINDOW", on_close)
root.mainloop()
