import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
from led_control import LEDController

import subprocess
import threading
import cv2
import numpy as np

class CameraStream:
    def __init__(self):
        self.buffer = b""
        self.frame = None
        self.running = True

        self.proc = subprocess.Popen([
            "libcamera-vid",
            "-t", "0",
            "--width", "640",
            "--height", "480",
            "--framerate", "15",
            "--codec", "mjpeg",
            "--inline",
            "-o", "-"
        ], stdout=subprocess.PIPE, bufsize=10**8)

        self.thread = threading.Thread(target=self._read_stream, daemon=True)
        self.thread.start()

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
                    jpg = self.buffer[start:end+2]
                    self.buffer = self.buffer[end+2:]

                    img = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                    if img is not None:
                        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                        self.frame = Image.fromarray(img)

            except Exception as e:
                print("Fehler beim Lesen des Streams:", e)

    def get_frame(self):
        return self.frame

    def stop(self):
        self.running = False
        self.proc.terminate()

def open_led_window():
    LEDController(root)
    
# GUI-Setup
root = tk.Tk()
root.title("Multispektralkamera Vorschau")

# Kameraanzeige
camera_label = ttk.Label(root)
camera_label.pack(padx=10, pady=10)

stream = CameraStream()

ttk.Button(root, text="LED Steuerung öffnen", command=open_led_window).pack(pady=10)


def update_gui():
    frame = stream.get_frame()
    if frame:
        imgtk = ImageTk.PhotoImage(image=frame)
        camera_label.imgtk = imgtk
        camera_label.configure(image=imgtk)
    root.after(50, update_gui)

update_gui()

def on_close():
    stream.stop()
    root.destroy()

root.protocol("WM_DELETE_WINDOW", on_close)
root.mainloop()
