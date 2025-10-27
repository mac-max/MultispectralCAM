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
import threading

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
            initialdir="/media/frank/ESD-USB/Images", defaultextension=".jpg", filetypes=[("JPEG-Dateien", "*.jpg"), ("Alle Dateien", "*.*")]
        )
        if not path:
            return
        self.status_label.config(text="Aufnahme läuft…")
        self.stream.capture_sensor_raw(filename=path, fmt="jpg")
        self.status_label.config(text=f"JPEG gespeichert: {path}")
        messagebox.showinfo("Aufnahme abgeschlossen", f"Bild gespeichert:\n{path}")

    def capture_raw(self):
        """Echte RAW/DNG-Aufnahme (Bayer 10 Bit)."""
        path = filedialog.asksaveasfilename(
            initialdir="/media/frank/ESD-USB/Images", defaultextension=".dng", filetypes=[("RAW DNG-Dateien", "*.dng"), ("Alle Dateien", "*.*")]
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
        """Öffnet oder erstellt den LED-Controller (GUI-Modus bevorzugt)."""
        if hasattr(self, "led_window") and getattr(self.led_window, "use_gui", False):
            try:
                self.led_window.window.lift()
                return
            except Exception:
                pass

        # Neuer Controller im GUI-Modus
        self.led_window = self.get_led_controller(force_gui=True)

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

        # Zustandsgrößen für adaptiven Regler
        self.step = 20.0
        self.min_step = 0.1
        self.prev_direction = 0
        self.loop_ms = 300
        self.step_var = tk.StringVar(value=f"{self.step:.2f} %")
        self._loop_busy = False  # Reentrancy-Guard
        self._last_error = None  # Für “Verbesserung?”
        self._stagnation_count = 0  # Zyklen ohne Verbesserung
        self._max_cycles = 200  # Sicherheitsabbbruch
        self._cycle_count = 0

        # Anzeige der Schrittgröße
        self.step_var = tk.StringVar(value=f"{self.step:.2f} %")

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
        # Wahl des Histogrammkanals
        self.hist_channel = tk.StringVar(value="Gray")  # Optionen: Gray, R, G, B

        ttk.Label(self, text="Histogrammkanal:",
                  foreground="white", background="#2e2e2e").pack(anchor="w", padx=10, pady=(10, 0))
        ttk.OptionMenu(self, self.hist_channel, self.hist_channel.get(), "Gray", "R", "G", "B").pack(
            fill="x", padx=10, pady=(0, 10)
        )

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

        ttk.Label(self, text="Aktuelle Schrittgröße:", foreground="white", background="#2e2e2e").pack(anchor="w",padx=10,pady=(10, 0))
        ttk.Label(self, textvariable=self.step_var, foreground="white", background="#2e2e2e").pack(anchor="w", padx=10)

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



    def _reset_leds_async(self, channel_only=True):
        def task():
            led = self.master.get_led_controller()
            if not led:
                return
            try:
                if channel_only:
                    ch = self.selected_channel.get()
                    if ch:
                        led.set_channel_by_name(ch, 0.0)
                else:
                    led.all_off()
            except Exception as e:
                print("[AUTO-LED] Reset fehlgeschlagen:", e)

        threading.Thread(target=task, daemon=True).start()

    # ------------------------------------------------------------
    # Start / Stop der Regelung
    # ------------------------------------------------------------
    def toggle_auto_led(self):
        if not self.active.get():
            # --- START ---
            # Reset interner Zustand
            self.step = 20.0
            self.prev_direction = 0
            self._last_error = None
            self._stagnation_count = 0
            self._cycle_count = 0
            self.step_var.set(f"{self.step:.2f} %")

            self._reset_leds_async(channel_only=False)

            self.active.set(True)
            self.status_label.config(text=f"Regelung aktiv für: {self.selected_channel.get()}")
            self.toggle_button.config(text="Regelung stoppen")
            self.run_auto_led()
        else:
            # --- STOP ---
            led = self.master.get_led_controller()
            self._reset_leds_async()
            self.active.set(False)
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
            self.after(self.loop_ms, self.run_auto_led)
            return

        # --- Histogrammkanal wählen ---
        f = np.array(frame)  # HxWx3, dtype=uint8 vom MJPEG-Stream
        sel = self.hist_channel.get()
        if sel == "R":
            chan = f[:, :, 0]
        elif sel == "G":
            chan = f[:, :, 1]
        elif sel == "B":
            chan = f[:, :, 2]
        else:
            # Gray: einfacher Mittelwert (alternativ Luma-Weighted)
            chan = np.mean(f, axis=2)

        chan = chan.astype(np.uint8, copy=False).ravel()
        hist, _ = np.histogram(chan, bins=256, range=(0, 256))
        total_pixels = max(1, chan.size)

        # Parameter
        low_limit = int(self.params["low_limit"].get())
        high_limit = int(self.params["high_limit"].get())
        low_fraction_target = float(self.params["low_fraction_target"].get())
        high_fraction_target = float(self.params["high_fraction_target"].get())
        eps = 0.002  # 0.2 %

        low_fraction = hist[:low_limit + 1].sum() / total_pixels
        high_fraction = hist[255 - high_limit:].sum() / total_pixels

        # Fehlermaß & Richtung (einheitliche Logik)
        err_dark = max(0.0, low_fraction - low_fraction_target)  # zu dunkel
        err_bright = max(0.0, high_fraction - high_fraction_target)  # zu hell
        error = err_dark - err_bright

        if error > eps:
            direction = +1  # heller
        elif error < -eps:
            direction = -1  # dunkler
        else:
            direction = 0

        channel_name = self.selected_channel.get()
        led = self.master.get_led_controller()
        if not led or not channel_name:
            self.after(self.loop_ms, self.run_auto_led)
            return

        # aktuellen Wert lesen (GUI/Headless robust)
        if hasattr(led, "sliders") and channel_name in getattr(led, "sliders", {}):
            current_value = float(led.sliders[channel_name].get())
        else:
            current_value = float(led.get_channel_value(channel_name) or 0.0)

        # Schritt-Anpassung
        # 1) Vorzeichenwechsel → Schritt halbieren (nur wenn direction != 0)
        if (self.prev_direction != 0) and (direction != 0) and (direction != self.prev_direction):
            self.step = max(self.step / 2.0, self.min_step)
            # optional: Debug
            # print(f"[AUTO-LED] sign flip → step={self.step:.3f}%")

        # 2) Keine Verbesserung → nach 2 Zyklen halbieren
        improved = True
        if self._last_error is not None:
            improved = (abs(error) < abs(self._last_error)) or (direction == 0)
            if not improved:
                self._stagnation_count += 1
                if self._stagnation_count >= 2:
                    self.step = max(self.step / 2.0, self.min_step)
                    self._stagnation_count = 0
                    # print(f"[AUTO-LED] stagnation → step={self.step:.3f}%")
            else:
                self._stagnation_count = 0

        self.step_var.set(f"{self.step:.2f} %")

        # Stellgröße anwenden – ausschließlich gemäß 'direction'
        new_value = current_value
        if direction != 0 and self.step > 0.0:
            new_value = max(0.0, min(100.0, current_value + direction * self.step))
            if abs(new_value - current_value) >= 1e-3:
                led.set_channel_by_name(channel_name, new_value)

        # Status
        self.status_label.config(
            text=f"{channel_name} [{sel}]: dunkel={low_fraction:.1%}, hell={high_fraction:.1%}, "
                 f"step={self.step:.2f}%, dir={direction:+d}"
        )

        # Zustände für nächste Iteration MERKEN (wichtig!)
        self.prev_direction = direction
        self._last_error = error
        self._cycle_count += 1

        # Abbruch: Ziele erreicht und Schritt klein genug ODER Sicherheitslimit
        if (direction == 0 and self.step <= self.min_step) or (self._cycle_count >= self._max_cycles):
            self.active.set(False)
            self.toggle_button.config(text="Regelung starten")
            self.status_label.config(text=f"Fertig: {channel_name} (step={self.step:.2f}%)")
            return

        # Weiter
        self.after(self.loop_ms, self.run_auto_led)


if __name__ == "__main__":
    app = SequenceRunnerGUI()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()
