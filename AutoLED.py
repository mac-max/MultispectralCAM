# === auto_led_core.py ===
import numpy as np
import threading

class AutoLEDCore:
    """
    Headless Auto-LED-Regler (kein Fenster). Läuft über Tk 'after' des Hosts.
    Host muss Properties/Mthds bereitstellen:
      - host.stream.get_frame()
      - host.get_led_controller(force_gui=False)
      - host.after(ms, callback)
    Optional: on_update(dict) Callback für Live-Status.
    """
    def __init__(self, host, on_update=None):
        self.host = host
        self.on_update = on_update  # callable(status_dict)
        # Regel-Parameter (Defaultwerte; können beim start() überschrieben werden)
        self.low_limit = 10
        self.high_limit = 10
        self.low_target = 0.05
        self.high_target = 0.05
        self.hist_channel = "Gray"   # "Gray","R","G","B"
        self.channel_name = None     # LED-Kanalname

        # Adaptive Schrittlogik
        self.step = 20.0
        self.min_step = 0.1
        self.prev_direction = 0
        self._last_error = None
        self._stagnation = 0
        self.loop_ms = 300
        self._active = False
        self._cycle = 0
        self._max_cycles = 200
        self._busy = False  # Reentrancy-Guard

        # Start-Reset asynchron (nur den geregelten Kanal)
        self._reset_thread = None

    @property
    def active(self):
        return self._active

    def start(self, channel_name, hist_channel="Gray", params=None, start_step=20.0):
        """Startet die Regelung ohne GUI."""
        if self._active:
            return
        self.channel_name = channel_name
        self.hist_channel = hist_channel

        if params:
            self.low_limit  = int(params.get("low_limit",  self.low_limit))
            self.high_limit = int(params.get("high_limit", self.high_limit))
            self.low_target  = float(params.get("low_fraction_target",  self.low_target))
            self.high_target = float(params.get("high_fraction_target", self.high_target))

        self.step = max(0.05, min(50.0, float(start_step)))
        self.prev_direction = 0
        self._last_error = None
        self._stagnation = 0
        self._cycle = 0

        # Kanal auf 0 % setzen (non-blocking)
        def _reset():
            led = self.host.get_led_controller(force_gui=False)
            if led and channel_name:
                try:
                    led.set_channel_by_name(channel_name, 0.0)
                except Exception as e:
                    print("[AutoLEDCore] Reset failed:", e)
        self._reset_thread = threading.Thread(target=_reset, daemon=True)
        self._reset_thread.start()

        self._active = True
        self._tick()

    def stop(self):
        self._active = False

    # --- interner Takt ---
    def _tick(self):
        if not self._active:
            return
        if self._busy:
            # falls ein Tick hängt, später nochmal
            self.host.after(self.loop_ms, self._tick)
            return
        self._busy = True

        try:
            frame = self.host.stream.get_frame()
            if frame is None:
                self._busy = False
                self.host.after(self.loop_ms, self._tick)
                return

            f = np.array(frame)  # HxWx3 uint8
            sel = self.hist_channel
            if sel == "R":
                chan = f[:, :, 0]
            elif sel == "G":
                chan = f[:, :, 1]
            elif sel == "B":
                chan = f[:, :, 2]
            else:  # Gray
                chan = np.mean(f, axis=2)
            chan = chan.astype(np.uint8, copy=False).ravel()

            hist, _ = np.histogram(chan, bins=256, range=(0, 256))
            total = max(1, chan.size)
            low_frac  = hist[: self.low_limit + 1].sum() / total
            high_frac = hist[255 - self.high_limit :].sum() / total

            # Fehlermaß
            err_dark   = max(0.0, low_frac  - self.low_target)
            err_bright = max(0.0, high_frac - self.high_target)
            error = err_dark - err_bright
            eps = 0.002

            if error > eps:
                direction = +1
            elif error < -eps:
                direction = -1
            else:
                direction = 0

            led = self.host.get_led_controller(force_gui=False)
            if not led or not self.channel_name:
                self._busy = False
                self.host.after(self.loop_ms, self._tick)
                return

            # aktuellen PWM lesen (GUI/Headless robust)
            if hasattr(led, "sliders") and self.channel_name in getattr(led, "sliders", {}):
                current = float(led.sliders[self.channel_name].get())
            else:
                current = float(led.get_channel_value(self.channel_name) or 0.0)

            # Schritt-Anpassung
            if (self.prev_direction != 0) and (direction != 0) and (direction != self.prev_direction):
                self.step = max(self.step / 2.0, self.min_step)

            improved = True
            if self._last_error is not None:
                improved = (abs(error) < abs(self._last_error)) or (direction == 0)
                if not improved:
                    self._stagnation += 1
                    if self._stagnation >= 2:
                        self.step = max(self.step / 2.0, self.min_step)
                        self._stagnation = 0
                else:
                    self._stagnation = 0

            # Stellgröße
            new_val = current
            if direction != 0 and self.step > 0.0:
                new_val = max(0.0, min(100.0, current + direction * self.step))
                if abs(new_val - current) >= 1e-3:
                    led.set_channel_by_name(self.channel_name, new_val)

            # Status-Callback
            if callable(self.on_update):
                self.on_update({
                    "channel": self.channel_name,
                    "hist_channel": self.hist_channel,
                    "low_fraction": low_frac,
                    "high_fraction": high_frac,
                    "direction": direction,
                    "step": self.step,
                    "pwm": new_val
                })

            # Fortschritt/Zustand merken
            self.prev_direction = direction
            self._last_error = error
            self._cycle += 1

            # Abbruchbedingungen
            if (direction == 0 and self.step <= self.min_step) or (self._cycle >= self._max_cycles):
                self._active = False
                return

        finally:
            self._busy = False
            if self._active:
                self.host.after(self.loop_ms, self._tick)
