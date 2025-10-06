import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from led_control import LEDController
from camera_settings import CameraSettings
from sensor_monitor import SensorMonitor
from camera_gui import CameraStream  # <- dein bestehender Streamcode


class SequenceRunnerGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Multispektralkamera – Sequence Runner")
        self.geometry("1200x800")
        self.configure(bg="#1e1e1e")

        # Kamera-Stream
        self.stream = CameraStream(width=640, height=480, framerate=15)
        self.is_live = True

        # GUI-Layout
        self._create_layout()
        self.update_gui()

    # -------------------------
    # Layout
    # -------------------------
    def _create_layout(self):
        # Linke Buttonleiste
        self.left_frame = ttk.Frame(self, width=200)
        self.left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)

        # Hauptanzeige
        self.main_frame = ttk.Frame(self)
        self.main_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Kamerabild
        self.image_label = tk.Label(self.main_frame, bg="black")
        self.image_label.pack(fill=tk.BOTH, expand=True)

        # Histogramm
        self.fig, self.ax = plt.subplots(figsize=(8, 2))
        self.fig.patch.set_facecolor("#1e1e1e")
        self.ax.set_facecolor("#1e1e1e")
        self.ax.tick_params(colors="white")
        self.ax.set_title("Histogramm", color="white")
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.main_frame)
        self.canvas.get_tk_widget().pack(fill=tk.X, expand=False)

        # Statuszeile
        self.status_label = tk.Label(
            self, text="Bereit", anchor="w", bg="#2e2e2e", fg="white"
        )
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)

        # Buttons
        self._create_buttons()

    def _create_buttons(self):
        buttons = [
            ("📷 Kameraeinstellungen", self.open_camera_settings),
            ("💡 LED Steuerung", self.open_led_controller),
            ("📈 Spektralsensor", self.open_sensor_monitor),
            ("🌞 Auto-LED starten", self.start_auto_led),
            ("❌ Beenden", self.on_close),
        ]
        for text, cmd in buttons:
            ttk.Button(self.left_frame, text=text, command=cmd).pack(fill=tk.X, pady=5, padx=5)

    # -------------------------
    # GUI-Update-Schleife
    # -------------------------
    def update_gui(self):
        frame = self.stream.get_frame()
        if frame:
            imgtk = ImageTk.PhotoImage(image=frame)
            self.image_label.imgtk = imgtk
            self.image_label.configure(image=imgtk)

            # Histogramm aktualisieren
            frame_np = np.array(frame)
            gray = np.mean(frame_np, axis=2).astype(np.uint8)
            hist = np.histogram(gray, bins=256, range=(0, 256))[0]

            self.ax.clear()
            self.ax.plot(hist, color="white")
            self.ax.set_facecolor("#1e1e1e")
            self.ax.set_xlim([0, 256])
            self.ax.set_title("Helligkeitshistogramm", color="white")
            self.ax.tick_params(colors="white")
            self.canvas.draw_idle()

        if self.is_live:
            self.after(100, self.update_gui)

    # -------------------------
    # Button-Aktionen
    # -------------------------
    def open_camera_settings(self):
        CameraSettings(self, self.stream)

    def open_led_controller(self):
        if hasattr(self, "led_window") and self.led_window.winfo_exists():
            self.led_window.lift()
            return
        self.led_window = LEDController(self)

    def open_sensor_monitor(self):
        SensorMonitor(self)

    def start_auto_led(self):
        # Platzhalter: LED-Autoregelung folgt im nächsten Schritt
        self.status_label.config(text="Auto-LED-Regelung noch nicht implementiert.")

    def on_close(self):
        self.is_live = False
        self.stream.stop()
        self.destroy()


if __name__ == "__main__":
    app = SequenceRunnerGUI()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()
