import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from camera_stream import CameraStream          # ← neue zentrale Kamera
from camera_settings import CameraSettings      # ← dein bestehender Dialog
from led_control import LEDController
from sensor_monitor import SensorMonitor


class SequenceRunnerGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Multispektralkamera – Sequence Runner")
        self.geometry("1200x800")
        self.configure(bg="#1e1e1e")

        # Zentrale Kamera-Instanz (kein Standalone-GUI)
        self.stream = CameraStream(width=640, height=480, framerate=15, standalone=False)
        self.is_live = True

        # GUI-Aufbau
        self._create_layout()
        self.update_gui()

    # ------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------
    def _create_layout(self):
        # Linke Button-Leiste
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

        self._create_buttons()

    def _create_buttons(self):
        buttons = [
            ("Kameraeinstellungen", self.open_camera_settings),
            ("LED Steuerung", self.open_led_controller),
            ("Sensorsignal", self.open_sensor_monitor),
            ("Einzelaufnahme (JPEG)", self.capture_jpeg),
            ("Einzelaufnahme (RAW)", self.capture_raw),
            ("Auto-LED starten", self.open_auto_led_dialog),
            ("Beenden", self.on_close),
        ]
        for text, cmd in buttons:
            ttk.Button(self.left_frame, text=text, command=cmd).pack(fill=tk.X, pady=5, padx=5)

    # ------------------------------------------------------------
    # Live-Vorschau
    # ------------------------------------------------------------
    def update_gui(self):
        frame = self.stream.get_frame()
        if frame:
            imgtk = ImageTk.PhotoImage(image=frame)
            self.image_label.imgtk = imgtk
            self.image_label.configure(image=imgtk)

            # Histogramm aktualisieren (RGB + Grau)
            frame_np = np.array(frame)
            r = frame_np[:, :, 0].flatten()
            g = frame_np[:, :, 1].flatten()
            b = frame_np[:, :, 2].flatten()
            gray = np.mean(frame_np, axis=2).astype(np.uint8).flatten()

            hist_r, _ = np.histogram(r, bins=256, range=(0, 256))
            hist_g, _ = np.histogram(g, bins=256, range=(0, 256))
            hist_b, _ = np.histogram(b, bins=256, range=(0, 256))
            hist_gray, _ = np.histogram(gray, bins=256, range=(0, 256))

            self.ax.clear()
            self.ax.set_facecolor("#1e1e1e")

            # Farbverteilungen
            self.ax.plot(hist_r, color="red", alpha=0.7, label="Rot")
            self.ax.plot(hist_g, color="lime", alpha=0.7, label="Grün")
            self.ax.plot(hist_b, color="cyan", alpha=0.7, label="Blau")

            # Grauwertverteilung (weiß)
            self.ax.plot(hist_gray, color="white", alpha=0.6, linewidth=1.0, label="Grau")

            self.ax.set_xlim([0, 256])
            self.ax.set_title("Helligkeitsverteilung (RGB)", color="white")
            self.ax.tick_params(colors="white")
            self.ax.legend(facecolor="#2e2e2e", edgecolor="#2e2e2e", labelcolor="white", loc="upper right")
            self.canvas.draw_idle()

        if self.is_live:
            self.after(100, self.update_gui)

    # ------------------------------------------------------------
    # Einzelbild-Aufnahmen
    # ------------------------------------------------------------
    def capture_jpeg(self):
        """Einzelaufnahme als JPEG speichern."""
        path = filedialog.asksaveasfilename(
            defaultextension=".jpg", filetypes=[("JPEG-Dateien", "*.jpg"), ("Alle Dateien", "*.*")]
        )
        if not path:
            return
        self.status_label.config(text="Aufnahme läuft…")
        self.stream.capture_raw(filename=path, fmt="jpg")
        self.status_label.config(text=f"JPEG gespeichert: {path}")
        messagebox.showinfo("Aufnahme abgeschlossen", f"Bild gespeichert:\n{path}")

    def capture_raw(self):
        """Echte RAW/DNG-Aufnahme (Bayer 10 Bit)."""
        path = filedialog.asksaveasfilename(
            defaultextension=".dng", filetypes=[("RAW DNG-Dateien", "*.dng"), ("Alle Dateien", "*.*")]
        )
        if not path:
            return
        self.status_label.config(text="RAW-Aufnahme läuft…")
        self.stream.capture_sensor_raw(filename=path)
        self.status_label.config(text=f"RAW gespeichert: {path}")
        messagebox.showinfo("RAW-Aufnahme abgeschlossen", f"RAW gespeichert:\n{path}")

    # ------------------------------------------------------------
    # Zusatzfunktionen
    # ------------------------------------------------------------
    def open_camera_settings(self):
        CameraSettings(self, self.stream)

    def get_led_controller(self, force_gui=False):
        """
        Gibt sicher eine gültige LEDController-Instanz zurück.
        Wenn keine existiert, wird sie erstellt:
          - mit GUI, falls 'force_gui=True' oder Tkinter-Kontext vorhanden,
          - sonst headless.
        """
        led = getattr(self, "led_window", None)

        # Prüfen, ob bestehender Controller gültig ist
        if led and hasattr(led, "get_all_channels"):
            return led

        try:
            from led_control import LEDController

            # Prüfen, ob GUI-Modus verfügbar ist
            use_gui = force_gui or hasattr(self, "master")
            mode_text = "mit GUI" if use_gui else "headless"

            print(f"[INFO] Kein aktiver LED-Controller gefunden – starte {mode_text}-Modus.")
            self.led_window = LEDController(use_gui=use_gui, master=getattr(self, "master", None))
            print(f"[INFO] LED-Controller ({mode_text}) erfolgreich initialisiert.")
            return self.led_window

        except Exception as e:
            from tkinter import messagebox
            messagebox.showerror("Fehler", f"LED-Controller konnte nicht initialisiert werden:\n{e}")
            return None


    def open_led_controller(self):
        self.led_window = self.get_led_controller(self, force_gui=True)

    def open_sensor_monitor(self):
        SensorMonitor(self)


    def open_auto_led_dialog(self):
        """Öffnet das Auto-LED-Regelungsfenster."""
        # Sicherstellen, dass LED-Controller verfügbar ist
        led = self.get_led_controller()
        if not led:
            return

        # Fenster öffnen
        if not hasattr(self, "auto_led_window") or not getattr(self.auto_led_window, "winfo_exists", lambda: False)():
            self.auto_led_window = AutoLEDDialog(self)
        else:
            self.auto_led_window.lift()

    # ------------------------------------------------------------
    # Beenden
    # ------------------------------------------------------------
    def on_close(self):
        self.is_live = False
        self.stream.stop()
        self.destroy()

class AutoLEDDialog(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.master = master
        self.title("Auto-LED Regelung")
        self.geometry("320x380")
        self.configure(bg="#2e2e2e")

        # Sicherstellen, dass LEDController existiert
        if not hasattr(self.master, "led_window") or not getattr(self.master.led_window, "pca_1", None):
            print("[AutoLED] Kein LED-Controller gefunden, starte headless Instanz.")
            from led_control import LEDController
            self.master.led_window = LEDController(use_gui=False)

        # Regelparameter
        self.params = {
            "low_limit": tk.IntVar(value=10),
            "high_limit": tk.IntVar(value=10),
            "low_fraction_target": tk.DoubleVar(value=0.05),
            "high_fraction_target": tk.DoubleVar(value=0.05),
            "step": tk.DoubleVar(value=2.0)
        }

        self.selected_channel = tk.StringVar(value="")
        self.active = tk.BooleanVar(value=False)

        self._build_ui()
        self._update_channel_list()

    # ------------------------------------------------------------
    # GUI-Aufbau
    # ------------------------------------------------------------
    def _build_ui(self):
        ttk.Label(self, text="LED-Kanal:", foreground="white", background="#2e2e2e").pack(anchor="w", padx=10, pady=(10, 0))
        self.channel_menu = ttk.OptionMenu(self, self.selected_channel, "")
        self.channel_menu.pack(fill="x", padx=10, pady=(0, 10))

        ttk.Label(self, text="Parameter:", foreground="white", background="#2e2e2e").pack(anchor="w", padx=10, pady=(5, 0))

        for key, label in [
            ("low_limit", "Dunkelgrenze [0–255]"),
            ("low_fraction_target", "max. Dunkelanteil"),
            ("high_limit", "Hellgrenze [0–255]"),
            ("high_fraction_target", "max. Hellanteil"),
            ("step", "Regelschritt [%]"),
        ]:
            ttk.Label(self, text=label, foreground="white", background="#2e2e2e").pack(anchor="w", padx=10, pady=(8, 0))
            ttk.Entry(self, textvariable=self.params[key]).pack(fill="x", padx=10)

        self.status_label = ttk.Label(self, text="Status: inaktiv", foreground="white", background="#2e2e2e")
        self.status_label.pack(fill="x", pady=10)

        self.toggle_button = ttk.Button(self, text="Regelung starten", command=self.toggle_auto_led)
        self.toggle_button.pack(pady=10)

        ttk.Button(self, text="Schließen", command=self.destroy).pack(pady=10)

    # ------------------------------------------------------------
    # Kanal-Liste aktualisieren
    # ------------------------------------------------------------
    def _update_channel_list(self):
        led = self.master.get_led_controller()
        if led is None:
            self.selected_channel.set("")
            return

        menu = self.channel_menu["menu"]
        menu.delete(0, "end")

        channels = led.get_all_channels()
        for name in channels:
            menu.add_command(label=name, command=lambda n=name: self.selected_channel.set(n))

        if not self.selected_channel.get() and channels:
            self.selected_channel.set(channels[0])

    # ------------------------------------------------------------
    # Start / Stop der Regelung
    # ------------------------------------------------------------
    def toggle_auto_led(self):
        if not hasattr(self.master, "led_window"):
            messagebox.showwarning("Hinweis", "Bitte zuerst LED-Fenster öffnen.")
            return

        if not self.selected_channel.get():
            messagebox.showwarning("Hinweis", "Bitte einen LED-Kanal auswählen.")
            return

        self.active.set(not self.active.get())

        if self.active.get():
            self.status_label.config(text=f"Regelung aktiv für: {self.selected_channel.get()}")
            self.toggle_button.config(text="Regelung stoppen")
            self.run_auto_led()
        else:
            self.status_label.config(text="Status: inaktiv")
            self.toggle_button.config(text="Regelung starten")

    # ------------------------------------------------------------
    # Regelalgorithmus (nur ein Kanal)
    # ------------------------------------------------------------
    def run_auto_led(self):
        if not self.active.get():
            return

        frame = self.master.stream.get_frame()
        if frame is None:
            self.after(500, self.run_auto_led)
            return

        frame_np = np.array(frame)
        gray = np.mean(frame_np, axis=2).astype(np.uint8)
        hist = np.histogram(gray, bins=256, range=(0, 256))[0]
        total_pixels = gray.size

        low_limit = self.params["low_limit"].get()
        high_limit = self.params["high_limit"].get()
        low_fraction_target = self.params["low_fraction_target"].get()
        high_fraction_target = self.params["high_fraction_target"].get()
        step = self.params["step"].get()

        low_count = hist[:low_limit + 1].sum()
        high_count = hist[255 - high_limit:].sum()
        low_fraction = low_count / total_pixels
        high_fraction = high_count / total_pixels

        channel_name = self.selected_channel.get()
        led = self.master.get_led_controller()


        if led:
            # Aktuellen Helligkeitswert lesen (unabhängig von GUI)
            if hasattr(led, "sliders") and channel_name in led.sliders:
                current_value = led.sliders[channel_name].get()
            else:
                current_value = led.get_channel_value(channel_name) or 0.0
            new_value = current_value

            if low_fraction > low_fraction_target:
                new_value = min(100, current_value + step)
            elif high_fraction > high_fraction_target:
                new_value = max(0, current_value - step)

            if new_value != current_value:
                led.set_channel_by_name(channel_name, new_value)
                print(f"[AUTO-LED] {channel_name}: {current_value:.1f} → {new_value:.1f}")

        self.status_label.config(
            text=f"{channel_name}: dunkel={low_fraction:.1%}, hell={high_fraction:.1%}"
        )

        # Wiederholung alle 1 s
        self.after(1000, self.run_auto_led)


if __name__ == "__main__":
    app = SequenceRunnerGUI()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()
