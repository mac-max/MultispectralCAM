# auto_led_dialog.py
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import numpy as np


class AutoLEDDialog(tk.Toplevel):
    """
    Auto-LED-Regelung auf Basis:
    - Live-Bild aus master.stream.get_frame()
    - LED-Steuerung über master.get_led_controller()
    Die Regelung arbeitet nicht-blockierend mit .after().
    """

    def __init__(self, master):
        super().__init__(master)
        self.master = master
        self.title("Auto-LED Regelung")
        self.geometry("320x420")
        self.configure(bg="#2e2e2e")

        # LED-Controller besorgen (headless bevorzugt)
        self.led = master.get_led_controller(force_gui=False)
        if not self.led:
            messagebox.showerror("Auto-LED", "LED-Controller ist nicht verfügbar.")
            self.destroy()
            return

        # --- Regelparameter (Tk-Variablen) ---
        self.low_limit = tk.IntVar(value=10)
        self.high_limit = tk.IntVar(value=10)
        self.low_fraction_target = tk.DoubleVar(value=0.05)
        self.high_fraction_target = tk.DoubleVar(value=0.05)
        self.start_step_var = tk.DoubleVar(value=20.0)  # Startwert für Schrittweite

        # Histogramm-Kanalwahl
        self.hist_channel = tk.StringVar(value="Gray")  # Gray, R, G, B

        # LED-Kanal
        self.selected_channel = tk.StringVar(value="")

        # Zustand des Reglers
        self.active = tk.BooleanVar(value=False)
        self.current_step = 20.0
        self.min_step = 0.1
        self.prev_direction = 0
        self.last_error = None
        self.stagnation_count = 0

        self.loop_ms = 800  # Regelintervall in ms
        self.step_label_var = tk.StringVar(value="Schritt: 20.0 %")
        self.pwm_label_var = tk.StringVar(value="PWM: 0.0 %")
        self.status_var = tk.StringVar(value="Status: inaktiv")

        self._build_ui()
        self._update_channel_list()
        
        self.update_idletasks()  # Layout berechnen lassen
        w = max(self.winfo_reqwidth(), 320)
        h = max(self.winfo_reqheight(), 550)  # Mindesthöhe
        self.geometry(f"{w}x{h}")

    # ---------------- UI ----------------

    def _build_ui(self):
        pad_x = 10

        ttk.Label(self, text="LED-Kanal:", foreground="white",
                  background="#2e2e2e").pack(anchor="w", padx=pad_x, pady=(10, 0))
        self.channel_menu = ttk.OptionMenu(self, self.selected_channel, "")
        self.channel_menu.pack(fill="x", padx=pad_x, pady=(0, 8))

        ttk.Label(self, text="Histogrammkanal:",
                  foreground="white", background="#2e2e2e").pack(anchor="w", padx=pad_x, pady=(4, 0))
        ttk.OptionMenu(self, self.hist_channel, self.hist_channel.get(),
                       "Gray", "R", "G", "B").pack(fill="x", padx=pad_x, pady=(0, 8))

        ttk.Label(self, text="Parameter:",
                  foreground="white", background="#2e2e2e").pack(anchor="w", padx=pad_x, pady=(6, 0))

        for var, label in [
            (self.low_limit, "Dunkelgrenze [0–255]"),
            (self.low_fraction_target, "max. Dunkelanteil"),
            (self.high_limit, "Hellgrenze [0–255]"),
            (self.high_fraction_target, "max. Hellanteil"),
            (self.start_step_var, "Start-Schritt [%]"),
        ]:
            ttk.Label(self, text=label, foreground="white",
                      background="#2e2e2e").pack(anchor="w", padx=pad_x, pady=(6, 0))
            ttk.Entry(self, textvariable=var).pack(fill="x", padx=pad_x)

        ttk.Label(self, textvariable=self.step_label_var,
                  foreground="white", background="#2e2e2e").pack(anchor="w", padx=pad_x, pady=(8, 0))
        ttk.Label(self, textvariable=self.pwm_label_var,
                  foreground="white", background="#2e2e2e").pack(anchor="w", padx=pad_x, pady=(2, 0))

        ttk.Label(self, textvariable=self.status_var,
                  foreground="white", background="#2e2e2e").pack(fill="x", padx=pad_x, pady=(8, 4))

        self.toggle_button = ttk.Button(self, text="Regelung starten",
                                        command=self.toggle_auto_led)
        self.toggle_button.pack(pady=(6, 4))

        ttk.Button(self, text="Schließen", command=self.destroy).pack(pady=(4, 10))

    def _update_channel_list(self):
        channels = []
        try:
            channels = self.led.get_all_channels()
        except Exception as e:
            print("[AutoLED] get_all_channels() fehlgeschlagen:", e)

        menu = self.channel_menu["menu"]
        menu.delete(0, "end")
        for name in channels:
            menu.add_command(label=name, command=lambda n=name: self.selected_channel.set(n))

        if not self.selected_channel.get() and channels:
            self.selected_channel.set(channels[0])

    # ---------------- Start/Stop ----------------

    def toggle_auto_led(self):
        if not self.active.get():
            # START
            ch = self.selected_channel.get()
            if not ch:
                messagebox.showwarning("Auto-LED", "Bitte erst einen LED-Kanal wählen.")
                return

            # internen Zustand zurücksetzen
            self.current_step = float(self.start_step_var.get() or 20.0)
            self.current_step = max(self.current_step, self.min_step)
            self.prev_direction = 0
            self.last_error = None
            self.stagnation_count = 0
            self.step_label_var.set(f"Schritt: {self.current_step:.2f} %")

            # gewählten Kanal auf 0 setzen (nicht blockierend)
            self._reset_single_channel_async(ch)

            self.active.set(True)
            self.status_var.set(f"Regelung aktiv für: {ch}")
            self.toggle_button.config(text="Regelung stoppen")

            self.after(self.loop_ms, self._run_loop)
        else:
            # STOP
            self.active.set(False)
            self.status_var.set("Status: inaktiv")
            self.toggle_button.config(text="Regelung starten")

    def _reset_single_channel_async(self, channel_name: str):
        def task():
            try:
                self.led.set_channel_by_name(channel_name, 0.0)
            except Exception as e:
                print("[AutoLED] Reset fehlgeschlagen:", e)

        threading.Thread(target=task, daemon=True).start()

    # ---------------- Haupt-Regelschleife ----------------

    def _run_loop(self):
        if not self.active.get():
            return

        # aktuelles Frame holen
        frame = getattr(self.master, "stream", None).get_frame() if hasattr(self.master, "stream") else None
        if frame is None:
            # kein Bild -> später noch einmal versuchen
            self.after(self.loop_ms, self._run_loop)
            return

        f = np.array(frame)  # HxWx3, uint8
        sel = self.hist_channel.get()

        if sel == "R":
            chan = f[:, :, 0]
        elif sel == "G":
            chan = f[:, :, 1]
        elif sel == "B":
            chan = f[:, :, 2]
        else:
            chan = np.mean(f, axis=2)

        chan = chan.astype(np.uint8, copy=False).ravel()

        hist, _ = np.histogram(chan, bins=256, range=(0, 256))
        total_pixels = max(1, chan.size)

        low_limit = int(self.low_limit.get())
        high_limit = int(self.high_limit.get())
        low_fraction_target = float(self.low_fraction_target.get())
        high_fraction_target = float(self.high_fraction_target.get())
        eps = 0.002  # 0.2 % Toleranz

        low_count = hist[: low_limit + 1].sum()
        high_count = hist[255 - high_limit:].sum()
        low_fraction = low_count / total_pixels
        high_fraction = high_count / total_pixels

        # Fehlermaß: positiv = zu dunkel (zu viel low), negativ = zu hell (zu viel high)
        err_dark = max(0.0, low_fraction - low_fraction_target)
        err_bright = max(0.0, high_fraction - high_fraction_target)
        error = err_dark - err_bright

        if error > eps:
            direction = +1  # heller machen
        elif error < -eps:
            direction = -1  # dunkler machen
        else:
            direction = 0

        channel_name = self.selected_channel.get()

        # aktuellen PWM-Wert lesen
        current_value = 0.0
        try:
            if hasattr(self.led, "sliders") and channel_name in self.led.sliders:
                current_value = float(self.led.sliders[channel_name].get())
            elif hasattr(self.led, "get_channel_value"):
                val = self.led.get_channel_value(channel_name)
                current_value = float(val or 0.0)
        except Exception:
            current_value = 0.0

        # Schrittweite adaptiv anpassen
        improved = True
        if self.last_error is not None:
            improved = (abs(error) < abs(self.last_error)) or (direction == 0)
            # Vorzeichenwechsel?
            if direction != 0 and self.prev_direction != 0 and direction != self.prev_direction:
                self.current_step = max(self.current_step / 2.0, self.min_step)
            elif not improved:
                self.stagnation_count += 1
                if self.stagnation_count >= 2:
                    self.current_step = max(self.current_step / 2.0, self.min_step)
                    self.stagnation_count = 0

        self.step_label_var.set(f"Schritt: {self.current_step:.2f} %")
        self.prev_direction = direction
        self.last_error = error

        # Stellgröße anpassen
        new_value = current_value
        if low_fraction > low_fraction_target:
            new_value = min(100.0, current_value + self.current_step)
        elif high_fraction > high_fraction_target:
            new_value = max(0.0, current_value - self.current_step)

        if new_value != current_value:
            try:
                self.led.set_channel_by_name(channel_name, new_value)
                print(f"[AUTO-LED] {channel_name}: {current_value:.1f} → {new_value:.1f}, "
                      f"lf={low_fraction:.3f}, hf={high_fraction:.3f}, step={self.current_step:.2f}")
            except Exception as e:
                print("[AUTO-LED] set_channel_by_name fehlgeschlagen:", e)

        self.pwm_label_var.set(f"PWM: {new_value:.1f} %")
        self.status_var.set(
            f"{channel_name} [{sel}] – dunkel={low_fraction:.1%}, hell={high_fraction:.1%}, dir={direction:+d}"
        )

        # nächster Zyklus
        self.after(self.loop_ms, self._run_loop)
