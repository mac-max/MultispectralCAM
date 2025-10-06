import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
import cv2
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from filter_controller import IRFilterController  # <- dein Modul
from led_controller import LEDController  # <-- Dein bestehendes LED GUI-Modul


# -------------------------
# Dummy CameraStream (Platzhalter)
# -------------------------
class CameraStream:
    def __init__(self, cap):
        self.cap = cap
        self.width = 640
        self.height = 480
        self.framerate = 30
        self.shutter = 10000
        self.gain = 1.0

    def reconfigure(self, width, height, framerate, shutter, gain):
        print(f"[CameraStream] Reconfigure: {width}x{height} @ {framerate}fps, shutter={shutter}, gain={gain}")
        self.width, self.height = width, height
        self.framerate = framerate
        self.shutter = shutter
        self.gain = gain

        # Beispielhafte Umsetzung:
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.cap.set(cv2.CAP_PROP_FPS, framerate)
        # shutter und gain: hängt vom Treiber ab
        try:
            self.cap.set(cv2.CAP_PROP_EXPOSURE, float(-np.log10(shutter / 30000)))
            self.cap.set(cv2.CAP_PROP_GAIN, float(gain))
        except Exception:
            pass


# -------------------------
# Kameraeinstellungen-Dialog
# -------------------------
class CameraSettings(tk.Toplevel):
    def __init__(self, master, camera_stream):
        super().__init__(master)
        self.title("Kameraeinstellungen")
        self.camera_stream = camera_stream

        self.ir_filter = IRFilterController()

        self.res_options = {
            "640x480 @59fps": (640, 480, 59),
            "1296x972 @46fps": (1296, 972, 46),
            "1920x1080 @32fps": (1920, 1080, 32),
            "2592x1944 @15fps": (2592, 1944, 15)
        }

        self.selected_res = tk.StringVar(value="640x480 @59fps")
        self.shutter_var = tk.IntVar(value=10000)
        self.gain_var = tk.DoubleVar(value=1.0)

        self.build_ui()

    def build_ui(self):
        frame = ttk.Frame(self)
        frame.pack(padx=10, pady=10, fill="x")

        ttk.Label(frame, text="Auflösung & FPS:").pack(anchor="w")
        res_menu = ttk.OptionMenu(frame, self.selected_res, self.selected_res.get(), *self.res_options.keys())
        res_menu.pack(fill="x", pady=(0, 10))

        ttk.Label(frame, text="Belichtungszeit [µs]:").pack(anchor="w")
        shutter_slider = ttk.Scale(frame, from_=100, to=30000, variable=self.shutter_var, orient="horizontal")
        shutter_slider.pack(fill="x", pady=(0, 10))
        ttk.Label(frame, textvariable=self.shutter_var).pack(anchor="e")

        ttk.Label(frame, text="Gain:").pack(anchor="w")
        gain_slider = ttk.Scale(frame, from_=1.0, to=16.0, variable=self.gain_var, orient="horizontal")
        gain_slider.pack(fill="x", pady=(0, 10))
        ttk.Label(frame, textvariable=self.gain_var).pack(anchor="e")

        ttk.Label(frame, text="IR-Filter:").pack(anchor="w", pady=(10, 0))
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill="x", pady=(0, 10))
        ttk.Button(btn_frame, text="Einschwenken", command=self.switch_filter_in).pack(side="left", expand=True, fill="x", padx=(0, 5))
        ttk.Button(btn_frame, text="Ausschwenken", command=self.switch_filter_out).pack(side="left", expand=True, fill="x", padx=(5, 0))

        ttk.Button(frame, text="Anwenden", command=self.apply_settings).pack(pady=(10, 0))

    def switch_filter_in(self):
        print("[INFO] IR-Filter wird eingeschwenkt.")
        self.ir_filter.switch_in()

    def switch_filter_out(self):
        print("[INFO] IR-Filter wird ausgeschwenkt.")
        self.ir_filter.switch_out()

    def apply_settings(self):
        res_label = self.selected_res.get()
        width, height, framerate = self.res_options[res_label]
        shutter = self.shutter_var.get()
        gain = round(self.gain_var.get(), 2)

        print(f"[INFO] Neue Kameraeinstellungen: {width}x{height}, {framerate}fps, shutter={shutter}, gain={gain}")
        self.camera_stream.reconfigure(width, height, framerate, shutter, gain)
        self.destroy()


# -------------------------
# Haupt-GUI
# -------------------------
class SequenceRunnerGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Multispektrale Kamera – Sequence Runner")
        self.geometry("1200x800")
        self.configure(bg="#1e1e1e")

        self.cap = cv2.VideoCapture(0)
        self.camera_stream = CameraStream(self.cap)
        self.is_live = False

        self._create_layout()

    def _create_layout(self):
        self.left_frame = ttk.Frame(self, width=200)
        self.left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)

        self.main_frame = ttk.Frame(self)
        self.main_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.image_label = tk.Label(self.main_frame, bg="black")
        self.image_label.pack(fill=tk.BOTH, expand=True)

        self.fig, self.ax = plt.subplots(figsize=(8, 2))
        self.fig.patch.set_facecolor("#1e1e1e")
        self.ax.set_facecolor("#1e1e1e")
        self.ax.tick_params(colors="white")
        self.ax.set_title("Histogramm", color="white")

        self.canvas = FigureCanvasTkAgg(self.fig, master=self.main_frame)
        self.canvas.get_tk_widget().pack(fill=tk.X, expand=False)

        self.status_label = tk.Label(self, text="Bereit", anchor="w", bg="#2e2e2e", fg="white")
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)

        self._create_buttons()

    def _create_buttons(self):
        buttons = [
            ("Kameraeinstellungen", self.open_camera_settings),
            ("LED Steuerung", self.open_led_controller),
            ("Auto-LED starten", self.start_auto_led),
            ("Live-Vorschau starten", self.start_live),
            ("Live-Vorschau stoppen", self.stop_live),
            ("Beenden", self.on_close),
        ]
        for text, cmd in buttons:
            ttk.Button(self.left_frame, text=text, command=cmd).pack(fill=tk.X, pady=5, padx=5)

    def start_live(self):
        if self.is_live:
            return
        if not self.cap.isOpened():
            messagebox.showerror("Fehler", "Keine Kamera gefunden!")
            return
        self.is_live = True
        self.status_label.config(text="Live-Vorschau läuft…")
        self.update_frame()

    def stop_live(self):
        self.is_live = False
        self.status_label.config(text="Live-Vorschau gestoppt")

    def open_led_controller(self):
        if hasattr(self, "led_window") and self.led_window.winfo_exists():
            self.led_window.lift()
            return
        self.led_window = LEDController(self)

    def start_auto_led(self):
        """Analysiert das Histogramm und zeigt Anteile der Extrembereiche."""
        if not self.is_live:
            tk.messagebox.showinfo("Hinweis", "Bitte zuerst Live-Vorschau starten.")
            return

        # Standardwerte (später konfigurierbar)
        low_limit = 10
        high_limit = 10
        low_fraction_target = 0.05
        high_fraction_target = 0.05

        # Letztes Bild abrufen
        ret, frame = self.cap.read()
        if not ret:
            return
        frame_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        hist = cv2.calcHist([frame_gray], [0], None, [256], [0, 256]).flatten()
        total_pixels = frame_gray.size

        # Bereiche berechnen
        low_count = hist[:low_limit + 1].sum()
        high_count = hist[255 - high_limit:].sum()

        low_fraction = low_count / total_pixels
        high_fraction = high_count / total_pixels

        print(f"[AUTO-LED] Dunkelanteil: {low_fraction:.3f}, Hellanteil: {high_fraction:.3f}")

        # Beispielhafte Steuerung (später PID-artig feinjustierbar)
        if hasattr(self, "led_window") and self.led_window.winfo_exists():
            for name in self.led_window.get_all_channels():
                current_value = self.led_window.sliders[name].get()
                new_value = current_value

                if low_fraction > low_fraction_target:
                    new_value = min(100, current_value + 2)
                elif high_fraction > high_fraction_target:
                    new_value = max(0, current_value - 2)

                if new_value != current_value:
                    self.led_window.set_channel_by_name(name, new_value)

            self.status_label.config(
                text=f"Auto-LED-Regelung: dunkel={low_fraction:.2%}, hell={high_fraction:.2%}"
            )

        # Nächste Messung in 1 s
        self.after(1000, self.start_auto_led)

    def update_frame(self):
        if not self.is_live:
            return
        ret, frame = self.cap.read()
        if not ret:
            self.after(100, self.update_frame)
            return
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(frame_rgb).resize((800, 500))
        imgtk = ImageTk.PhotoImage(image=img)
        self.image_label.imgtk = imgtk
        self.image_label.config(image=imgtk)

        # Histogramm aktualisieren
        self.ax.clear()
        self.ax.set_facecolor("#1e1e1e")
        for i, col in enumerate(("r", "g", "b")):
            hist = cv2.calcHist([frame_rgb], [i], None, [256], [0, 256])
            self.ax.plot(hist, color=col)
        self.ax.set_xlim([0, 256])
        self.ax.set_title("RGB-Histogramm", color="white")
        self.ax.tick_params(colors="white")
        self.canvas.draw_idle()

        self.after(50, self.update_frame)

    def open_camera_settings(self):
        CameraSettings(self, self.camera_stream)

    def on_close(self):
        self.is_live = False
        if self.cap and self.cap.isOpened():
            self.cap.release()
        self.destroy()


if __name__ == "__main__":
    app = SequenceRunnerGUI()
    app.mainloop()
