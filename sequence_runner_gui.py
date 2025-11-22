import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import numpy as np
from PIL import ImageTk

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from camera_stream import CameraStream
from auto_led_dialog import AutoLEDDialog

class SequenceRunnerGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Multispektral – Vorschau")
        self.configure(bg="#2b2b2b")
        self.geometry("1060x660")

        # ---- Layout ----
        self.left = ttk.Frame(self)
        self.left.pack(side="left", fill="y", padx=8, pady=8)

        self.main = ttk.Frame(self)
        self.main.pack(side="left", fill="both", expand=True, padx=(0, 8), pady=8)

        # Bildanzeige
        self.image_label = ttk.Label(self.main)
        self.image_label.pack(fill="both", expand=True)

        # Histogramm über pyplot
        self.fig, self.ax = plt.subplots(figsize=(5.5, 2.4), dpi=100)
        self.fig.patch.set_facecolor("#1e1e1e")
        self.ax.set_facecolor("#1e1e1e")
        self.ax.tick_params(colors="white")
        self.ax.spines["bottom"].set_color("white")
        self.ax.spines["left"].set_color("white")
        self.ax.spines["top"].set_color("#444444")
        self.ax.spines["right"].set_color("#444444")

        self.canvas = FigureCanvasTkAgg(self.fig, master=self.main)
        self.canvas.get_tk_widget().pack(fill="x")

        # ---- Controls (links) ----
        ttk.Label(self.left, text="Funktionen").pack(pady=(0, 6), fill="x")

        ttk.Button(self.left, text="Kameraeinstellungen", command=self.open_camera_settings)\
            .pack(pady=2, fill="x")
        ttk.Button(self.left, text="LED Steuerung", command=self.open_led_controller)\
            .pack(pady=2, fill="x")
        ttk.Button(self.left, text="Sensorsignal", command=self.open_sensor_monitor)\
            .pack(pady=2, fill="x")

        ttk.Separator(self.left).pack(pady=6, fill="x")

        ttk.Button(self.left, text="Einzelaufnahme (JPEG)", command=self.capture_jpeg)\
            .pack(pady=2, fill="x")
        ttk.Button(self.left, text="Einzelaufnahme (RAW)", command=self.capture_raw)\
            .pack(pady=2, fill="x")

        ttk.Separator(self.left).pack(pady=6, fill="x")

        ttk.Button(self.left, text="Auto-LED starten", command=self.start_auto_led)\
            .pack(pady=2, fill="x")

        self.hist_log = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            self.left,
            text="Histogramm: log",
            variable=self.hist_log,
            command=self.update_gui_once,
        ).pack(pady=6, fill="x")

        self.live_enabled = tk.BooleanVar(value=False)
        self._live_job = None
        self.btn_live = ttk.Button(self.left, text="Live: AN", command=self.toggle_live)
        self.btn_live.pack(pady=2, fill="x")

        ttk.Separator(self.left).pack(pady=6, fill="x")
        ttk.Button(self.left, text="Beenden", command=self.on_close).pack(pady=2, fill="x")

        # ---- Kamera-Stream ----
        self.stream = CameraStream(width=640, height=480, framerate=15)
        self.start_live()

        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---------- LED Controller Access ----------

    def get_led_controller(self, force_gui: bool = False):
        led = getattr(self, "led_window", None)
        try:
            from led_control import LEDController  # deine Klasse
        except Exception as e:
            messagebox.showerror("LED", f"LED-Controller nicht verfügbar:\n{e}")
            return None

        if led and hasattr(led, "get_all_channels"):
            if force_gui and not getattr(led, "use_gui", False):
                self.led_window = LEDController(use_gui=True, master=self)
            return self.led_window

        try:
            self.led_window = LEDController(use_gui=bool(force_gui),
                                            master=self if force_gui else None)
            return self.led_window
        except Exception as e:
            messagebox.showerror("LED", f"LED-Controller konnte nicht gestartet werden:\n{e}")
            return None

    # ---------- Button-Callbacks ----------

    def open_camera_settings(self):
        try:
            from camera_settings import CameraSettings
        except Exception as e:
            messagebox.showerror("Kameraeinstellungen",
                                 f"Modul camera_settings nicht verfügbar:\n{e}")
            return
        CameraSettings(self, self.stream)

    def open_led_controller(self):
        led = self.get_led_controller(force_gui=True)
        if not led:
            return
        try:
            if hasattr(led, "window") and led.window:
                led.window.lift()
        except Exception:
            pass

    def open_sensor_monitor(self):
        try:
            from sensor_monitor import SensorMonitor
        except Exception as e:
            messagebox.showerror("Sensorsignal",
                                 f"Modul sensor_monitor nicht verfügbar:\n{e}")
            return
        SensorMonitor(self)

    def capture_jpeg(self):
        path = filedialog.asksaveasfilename(
            title="Speichern als JPEG",
            defaultextension=".jpg",
            filetypes=[
                ("JPEG", "*.jpg;*.jpeg"),
                ("PNG", "*.png"),
                ("TIFF", "*.tiff"),
                ("BMP", "*.bmp"),
            ],
        )
        if not path:
            return
        try:
            ext = path.split(".")[-1].lower()
            fmt = "jpg" if ext in ("jpg", "jpeg") else ext
            out = self.stream.capture_still(path, fmt=fmt)
            messagebox.showinfo("Einzelaufnahme", f"Gespeichert:\n{out}")
        except Exception as e:
            messagebox.showerror("Einzelaufnahme",
                                 f"Fehler bei JPEG/PNG/TIFF/BMP:\n{e}")

    def capture_raw(self):
        path = filedialog.asksaveasfilename(
            title="Speichern als DNG",
            defaultextension=".dng",
            filetypes=[("DNG (RAW)", "*.dng")],
        )
        if not path:
            return
        try:
            out = self.stream.capture_raw_dng(path, both=False)
            messagebox.showinfo("RAW-Aufnahme", f"DNG gespeichert:\n{out}")
        except Exception as e:
            messagebox.showerror("RAW-Aufnahme",
                                 f"Fehler bei DNG:\n{e}")

    def start_auto_led(self):
        # GUI-Dialog bevorzugen
        try:
            from auto_led_dialog import AutoLEDDialog
            AutoLEDDialog(self)
            return
        except Exception:
            pass

        # Fallback: Headless-Core
        try:
            from auto_led_core import AutoLEDCore
        except Exception as e:
            messagebox.showerror("Auto-LED",
                                 f"Weder Dialog noch Core verfügbar:\n{e}")
            return

        led = self.get_led_controller(force_gui=False)
        if not led:
            return
        channels = led.get_all_channels()
        if not channels:
            messagebox.showwarning("Auto-LED", "Keine LED-Kanäle gefunden.")
            return

        def on_update(st):
            self.title(
                f"Auto-LED {st['channel']}  PWM {st['pwm']:.1f}%  step {st['step']:.2f}%"
            )

        self.auto_led_core = AutoLEDCore(self, on_update=on_update)
        params = dict(
            low_limit=10,
            high_limit=10,
            low_fraction_target=0.05,
            high_fraction_target=0.05,
        )
        self.auto_led_core.start(
            channels[0], hist_channel="Gray", params=params, start_step=20.0
        )
        messagebox.showinfo(
            "Auto-LED", f"Headless-Regelung gestartet für: {channels[0]}"
        )

    # ---------- Live handling ----------

    def toggle_live(self):
        if self.live_enabled.get():
            self.stop_live()
        else:
            self.start_live()

    def start_live(self):
        self.live_enabled.set(True)
        self.btn_live.config(text="Live: AUS")
        if hasattr(self.stream, "preview_paused"):
            self.stream.preview_paused = False
        self.update_gui()

    def stop_live(self):
        self.live_enabled.set(False)
        self.btn_live.config(text="Live: AN")
        if getattr(self, "_live_job", None):
            try:
                self.after_cancel(self._live_job)
            except Exception:
                pass
            self._live_job = None
        if hasattr(self.stream, "preview_paused"):
            self.stream.preview_paused = True

    # ---------- Rendering ----------

    def update_gui(self):
        if not self.live_enabled.get():
            return

        frame = self.stream.get_frame()
        if frame:
            imgtk = ImageTk.PhotoImage(image=frame)
            self.image_label.imgtk = imgtk
            self.image_label.configure(image=imgtk)
            try:
                self._render_histogram(np.array(frame))
            except Exception:
                pass

        self._live_job = self.after(100, self.update_gui)

    def update_gui_once(self):
        frame = self.stream.get_frame()
        if not frame:
            return
        imgtk = ImageTk.PhotoImage(image=frame)
        self.image_label.imgtk = imgtk
        self.image_label.configure(image=imgtk)
        self._render_histogram(np.array(frame))

    def _render_histogram(self, frame_np: np.ndarray):
        r = frame_np[:, :, 0].ravel()
        g = frame_np[:, :, 1].ravel()
        b = frame_np[:, :, 2].ravel()
        gray = np.mean(frame_np, axis=2).astype(np.uint8).ravel()

        hist_r, _ = np.histogram(r, bins=256, range=(0, 256))
        hist_g, _ = np.histogram(g, bins=256, range=(0, 256))
        hist_b, _ = np.histogram(b, bins=256, range=(0, 256))
        hist_y, _ = np.histogram(gray, bins=256, range=(0, 256))

        self.ax.clear()
        self.ax.set_facecolor("#1e1e1e")

        if self.hist_log.get():
            hist_r = np.where(hist_r == 0, 1, hist_r)
            hist_g = np.where(hist_g == 0, 1, hist_g)
            hist_b = np.where(hist_b == 0, 1, hist_b)
            hist_y = np.where(hist_y == 0, 1, hist_y)
            self.ax.set_yscale("log")
            self.ax.set_title("Histogramm (log)", color="#dddddd")
        else:
            self.ax.set_yscale("linear")
            self.ax.set_title("Histogramm (linear)", color="#dddddd")

        # gedeckte Farben
        self.ax.plot(hist_r, label="R", color="#e57373", alpha=0.8)
        self.ax.plot(hist_g, label="G", color="#81c784", alpha=0.8)
        self.ax.plot(hist_b, label="B", color="#64b5f6", alpha=0.8)
        self.ax.plot(hist_y, label="Gray", color="#eeeeee", alpha=0.9, linewidth=1.2)

        self.ax.set_xlim(0, 256)
        self.ax.tick_params(colors="#dddddd")
        for spine in self.ax.spines.values():
            spine.set_color("#888888")
        leg = self.ax.legend(
            facecolor="#2e2e2e",
            edgecolor="#444444",
            labelcolor="#dddddd",
            loc="upper right",
        )
        for text in leg.get_texts():
            text.set_color("#dddddd")

        self.canvas.draw_idle()

    # ---------- Beenden ----------

    def on_close(self):
        if getattr(self, "_live_job", None):
            try:
                self.after_cancel(self._live_job)
            except Exception:
                pass
            self._live_job = None
        if hasattr(self.stream, "preview_paused"):
            self.stream.preview_paused = False
        try:
            self.stream.stop()
        finally:
            self.destroy()


if __name__ == "__main__":
    app = SequenceRunnerGUI()
    app.mainloop()
