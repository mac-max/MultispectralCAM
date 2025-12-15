# sequence_dialog.py
import os
import json
import time
import threading
from dataclasses import dataclass, asdict
from datetime import datetime

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import numpy as np

# Optional IR Filter
try:
    from filter_controller import IRFilterController
except Exception:
    IRFilterController = None


@dataclass
class ChannelPlan:
    name: str
    enabled: bool = True

    mode: str = "fixed"     # "fixed" oder "auto"
    pwm: float = 10.0       # nur für fixed

    hist_channel: str = "Gray"   # <<< NEU: pro Kanal

    jpeg: bool = True
    raw: bool = False



@dataclass
class SequencePlan:
    save_dir: str = ""
    repeat_ir: bool = False           # ohne/mit IR Filter wiederholen
    ir_states: list = None            # ["OUT","IN"] oder nur ["OUT"]
    hist_channel: str = "Gray"        # für Auto-LED: Gray/R/G/B

    # Auto-LED Parameter (global)
    low_limit: int = 10
    high_limit: int = 10
    low_fraction_target: float = 0.05
    high_fraction_target: float = 0.05
    start_step: float = 20.0
    min_step: float = 0.1
    eps: float = 0.002
    loop_ms: int = 800
    max_cycles: int = 120

    channels: list = None             # list[ChannelPlan]


class SequenceDialog(tk.Toplevel):
    """
    Fenster zum Erstellen und Ausführen einer Aufnahmesequenz.
    Erwartet master:
      - master.stream (CameraStream)
      - master.get_led_controller(force_gui=False)
    Optional:
      - filter_controller.IRFilterController verfügbar
    """

    def __init__(self, master):
        super().__init__(master)

        style = ttk.Style(self)
        try:
            style.theme_use("clam")  # besser “themed” anpassbar
        except Exception:
            pass

        # Grundfarben
        BG = "#2e2e2e"
        FG = "#dddddd"
        FIELD = "#3a3a3a"
        BORDER = "#444444"

        self.configure(bg=BG)

        style.configure(".", background=BG, foreground=FG)
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=FG)
        style.configure("TLabelframe", background=BG, foreground=FG, bordercolor=BORDER)
        style.configure("TLabelframe.Label", background=BG, foreground=FG)
        style.configure("TButton", background=FIELD, foreground=FG)
        style.map("TButton", background=[("active", "#444444")])

        style.configure("TCheckbutton", background=BG, foreground=FG)
        style.map("TCheckbutton", background=[("active", BG)], foreground=[("active", FG)])

        style.configure("TEntry", fieldbackground=FIELD, foreground=FG, insertcolor=FG)
        style.configure("TCombobox", fieldbackground=FIELD, background=FIELD, foreground=FG)
        style.configure("TMenubutton", background=FIELD, foreground=FG)

        self.master = master
        self.title("Aufnahmesequenz")
        self.geometry("780x520")
        self.configure(bg="#2e2e2e")

        # LED Controller (headless bevorzugt)
        self.led = self.master.get_led_controller(force_gui=False)
        if not self.led:
            messagebox.showerror("Sequenz", "LED-Controller nicht verfügbar.")
            self.destroy()
            return

        self.stream = getattr(self.master, "stream", None)
        if self.stream is None:
            messagebox.showerror("Sequenz", "Kein CameraStream im Master gefunden (master.stream fehlt).")
            self.destroy()
            return

        # IR Filter optional
        self.ir_filter = None
        self.ir_available = False
        if IRFilterController is not None:
            try:
                self.ir_filter = IRFilterController()
                self.ir_available = True
            except Exception:
                self.ir_available = False

        # --- Plan State (Tk Vars) ---
        self.save_dir_var = tk.StringVar(value=os.path.expanduser("~/MultispectralCAM_Data"))
        self.repeat_ir_var = tk.BooleanVar(value=False)
        self.hist_channel_var = tk.StringVar(value="Gray")

        self.low_limit_var = tk.IntVar(value=10)
        self.high_limit_var = tk.IntVar(value=10)
        self.low_frac_var = tk.DoubleVar(value=0.05)
        self.high_frac_var = tk.DoubleVar(value=0.05)
        self.start_step_var = tk.DoubleVar(value=20.0)
        self.min_step_var = tk.DoubleVar(value=0.1)
        self.loop_ms_var = tk.IntVar(value=800)
        self.max_cycles_var = tk.IntVar(value=120)

        self.status_var = tk.StringVar(value="Status: bereit")
        self.progress_var = tk.StringVar(value="")

        # Per-channel widgets
        self.channel_rows = []  # list[dict] with vars + name

        self._build_ui()
        self._populate_channels()

        self._running = False
        self._thread = None

    # ---------------- UI ----------------

    def _build_ui(self):
        pad = dict(padx=10, pady=8)

        top = ttk.Frame(self)
        top.pack(fill="x", **pad)

        ttk.Label(top, text="Speicherort:").grid(row=0, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.save_dir_var).grid(row=0, column=1, sticky="ew", padx=(6, 6))
        ttk.Button(top, text="…", command=self._choose_dir).grid(row=0, column=2, sticky="e")
        top.columnconfigure(1, weight=1)

        opt = ttk.Frame(self)
        opt.pack(fill="x", **pad)

        ttk.Checkbutton(opt, text="Schleife ohne/mit IR-Filter wiederholen",
                        variable=self.repeat_ir_var,
                        state=("normal" if self.ir_available else "disabled")).grid(row=0, column=0, sticky="w")

        ttk.Label(opt, text="Auto-LED Histogrammkanal:").grid(row=0, column=1, sticky="e", padx=(12, 0))
        ttk.OptionMenu(opt, self.hist_channel_var, self.hist_channel_var.get(),
                       "Gray", "R", "G", "B").grid(row=0, column=2, sticky="w", padx=(6, 0))

        # Auto-LED Parameter (kompakt)
        auto = ttk.LabelFrame(self, text="Auto-LED Parameter (global)")
        auto.pack(fill="x", **pad)

        def add_row(r, c, text, var, w=8):
            ttk.Label(auto, text=text).grid(row=r, column=c, sticky="w", padx=(6 if c else 0, 0), pady=2)
            ttk.Entry(auto, textvariable=var, width=w).grid(row=r, column=c+1, sticky="w", padx=(4, 10), pady=2)

        add_row(0, 0, "low_limit", self.low_limit_var)
        add_row(0, 2, "low_frac", self.low_frac_var)
        add_row(0, 4, "high_limit", self.high_limit_var)
        add_row(0, 6, "high_frac", self.high_frac_var)

        add_row(1, 0, "start_step %", self.start_step_var)
        add_row(1, 2, "min_step %", self.min_step_var)
        add_row(1, 4, "loop_ms", self.loop_ms_var)
        add_row(1, 6, "max_cycles", self.max_cycles_var)

        # Channel table (scrollable)
        mid = ttk.LabelFrame(self, text="Kanäle")
        mid.pack(fill="both", expand=True, **pad)

        canvas = tk.Canvas(mid, bg="#2e2e2e", highlightthickness=0)
        scroll = ttk.Scrollbar(mid, orient="vertical", command=canvas.yview)
        self.rows_frame = ttk.Frame(canvas)

        self.rows_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self.rows_frame, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)

        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        # Header
        hdr = ttk.Frame(self.rows_frame)
        hdr.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 2))

        headings = ["Use", "Kanal", "Mode", "PWM %", "Hist", "JPEG", "RAW"]
        widths = [6, 8, 10, 8, 7, 6, 6]
        for i, (h, w) in enumerate(zip(headings, widths)):
            ttk.Label(hdr, text=h).grid(row=0, column=i, sticky="w", padx=(0, 10))
            hdr.columnconfigure(i, minsize=w*8)

        # Bottom buttons/status
        bot = ttk.Frame(self)
        bot.pack(fill="x", **pad)

        ttk.Button(bot, text="Einstellungen speichern…", command=self.save_plan).grid(row=0, column=0, padx=(0, 6))
        ttk.Button(bot, text="Einstellungen laden…", command=self.load_plan).grid(row=0, column=1, padx=(0, 18))

        self.start_btn = ttk.Button(bot, text="Messung starten", command=self.start_sequence)
        self.start_btn.grid(row=0, column=2, padx=(0, 6))

        ttk.Button(bot, text="Schließen", command=self._on_close).grid(row=0, column=3)

        ttk.Label(bot, textvariable=self.status_var).grid(row=1, column=0, columnspan=4, sticky="w", pady=(10, 0))
        ttk.Label(bot, textvariable=self.progress_var).grid(row=2, column=0, columnspan=4, sticky="w", pady=(2, 0))

    def _choose_dir(self):
        d = filedialog.askdirectory(title="Speicherort wählen", initialdir=self.save_dir_var.get())
        if d:
            self.save_dir_var.set(d)

    def _populate_channels(self):
        for w in self.rows_frame.winfo_children():
            if w is not None:
                # Header behalten (row 0). Alles ab row>=1 löschen.
                info = str(w)
        # Lösche alte rows (aber nicht den Header)
        for child in list(self.rows_frame.children.values()):
            # Header-Frame hat row=0, wir löschen nur die Row-Frames später:
            pass

        # Wir bauen Rows neu ab row=1:
        # (Einfacher: wir merken rows in channel_rows und zerstören nur deren frame)
        for row in self.channel_rows:
            try:
                row["frame"].destroy()
            except Exception:
                pass
        self.channel_rows = []

        try:
            channels = self.led.get_all_channels()
        except Exception as e:
            messagebox.showerror("Sequenz", f"Konnte LED-Kanäle nicht lesen:\n{e}")
            channels = []

        for idx, ch_name in enumerate(channels, start=1):
            frm = ttk.Frame(self.rows_frame)
            frm.grid(row=idx, column=0, sticky="ew", padx=6, pady=2)

            enabled = tk.BooleanVar(value=True)
            mode = tk.StringVar(value="fixed")
            pwm = tk.DoubleVar(value=10.0)
            jpeg = tk.BooleanVar(value=True)
            raw = tk.BooleanVar(value=False)
            hist_ch = tk.StringVar(value="Gray")

            ttk.Checkbutton(frm, variable=enabled).grid(row=0, column=0, sticky="w", padx=(0, 10))
            ttk.Label(frm, text=ch_name).grid(row=0, column=1, sticky="w", padx=(0, 10))
            ttk.OptionMenu(frm, mode, mode.get(), "fixed", "auto").grid(row=0, column=2, sticky="w", padx=(0, 10))
            ttk.Entry(frm, textvariable=pwm, width=8).grid(row=0, column=3, sticky="w", padx=(0, 14))
            ttk.OptionMenu(frm, hist_ch, hist_ch.get(), "Gray", "R", "G", "B").grid(row=0, column=4, sticky="w", padx=(0, 14))
            ttk.Checkbutton(frm, variable=jpeg).grid(row=0, column=4, sticky="w", padx=(0, 18))
            ttk.Checkbutton(frm, variable=raw).grid(row=0, column=5, sticky="w")

            self.channel_rows.append({
                "frame": frm,
                "name": ch_name,
                "enabled": enabled,
                "mode": mode,
                "pwm": pwm,
                "hist_channel": hist_ch,
                "jpeg": jpeg,
                "raw": raw,
            })

    # ---------------- Plan Save/Load ----------------

    def _collect_plan(self) -> SequencePlan:
        plan = SequencePlan()
        plan.save_dir = os.path.expanduser(self.save_dir_var.get())
        plan.repeat_ir = bool(self.repeat_ir_var.get())
        plan.ir_states = ["OUT", "IN"] if plan.repeat_ir else ["OUT"]
        plan.hist_channel = self.hist_channel_var.get()

        plan.low_limit = int(self.low_limit_var.get())
        plan.high_limit = int(self.high_limit_var.get())
        plan.low_fraction_target = float(self.low_frac_var.get())
        plan.high_fraction_target = float(self.high_frac_var.get())
        plan.start_step = float(self.start_step_var.get())
        plan.min_step = float(self.min_step_var.get())
        plan.loop_ms = int(self.loop_ms_var.get())
        plan.max_cycles = int(self.max_cycles_var.get())

        plan.channels = []
        for row in self.channel_rows:
            cp = ChannelPlan(
                name=row["name"],
                enabled=bool(row["enabled"].get()),
                mode=row["mode"].get(),
                pwm=float(row["pwm"].get()),
                hist_channel=row["hist_channel"].get(),
                jpeg=bool(row["jpeg"].get()),
                raw=bool(row["raw"].get()),
            )
            plan.channels.append(cp)

        return plan

    def _apply_plan(self, plan: SequencePlan):
        self.save_dir_var.set(plan.save_dir or self.save_dir_var.get())
        self.repeat_ir_var.set(bool(plan.repeat_ir))
        self.hist_channel_var.set(plan.hist_channel or "Gray")

        self.low_limit_var.set(int(plan.low_limit))
        self.high_limit_var.set(int(plan.high_limit))
        self.low_frac_var.set(float(plan.low_fraction_target))
        self.high_frac_var.set(float(plan.high_fraction_target))
        self.start_step_var.set(float(plan.start_step))
        self.min_step_var.set(float(plan.min_step))
        self.loop_ms_var.set(int(plan.loop_ms))
        self.max_cycles_var.set(int(plan.max_cycles))

        # rows nach name mappen
        row_by_name = {r["name"]: r for r in self.channel_rows}
        if plan.channels:
            for cp in plan.channels:
                if cp.name in row_by_name:
                    r = row_by_name[cp.name]
                    r["enabled"].set(bool(cp.enabled))
                    r["mode"].set(cp.mode)
                    r["pwm"].set(float(cp.pwm))
                    r["hist_channel"].set(cp.hist_channel or "Gray")
                    r["jpeg"].set(bool(cp.jpeg))
                    r["raw"].set(bool(cp.raw))

    def save_plan(self):
        plan = self._collect_plan()
        path = filedialog.asksaveasfilename(
            title="Sequenz-Einstellungen speichern",
            defaultextension=".json",
            filetypes=[("JSON", "*.json")]
        )
        if not path:
            return
        try:
            data = asdict(plan)
            # dataclasses -> list of dict ok
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            self.status_var.set(f"Status: gespeichert: {path}")
        except Exception as e:
            messagebox.showerror("Speichern", f"Konnte nicht speichern:\n{e}")

    def load_plan(self):
        path = filedialog.askopenfilename(
            title="Sequenz-Einstellungen laden",
            filetypes=[("JSON", "*.json")]
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            plan = SequencePlan(**{k: data.get(k) for k in data.keys() if k != "channels"})
            # channels separat
            ch_list = []
            for c in data.get("channels", []):
                ch_list.append(ChannelPlan(**c))
            plan.channels = ch_list
            self._apply_plan(plan)
            self.status_var.set(f"Status: geladen: {path}")
        except Exception as e:
            messagebox.showerror("Laden", f"Konnte nicht laden:\n{e}")

    # ---------------- Run Sequence ----------------

    def start_sequence(self):
        if self._running:
            messagebox.showinfo("Sequenz", "Messung läuft bereits.")
            return

        plan = self._collect_plan()
        if not plan.save_dir:
            messagebox.showwarning("Sequenz", "Bitte Speicherort wählen.")
            return

        # snapshot: channels, etc.
        enabled_channels = [c for c in plan.channels if c.enabled]
        if not enabled_channels:
            messagebox.showwarning("Sequenz", "Keine Kanäle ausgewählt.")
            return

        os.makedirs(plan.save_dir, exist_ok=True)

        self._running = True
        self.start_btn.config(state="disabled")
        self.status_var.set("Status: Messung läuft …")
        self.progress_var.set("")

        self._thread = threading.Thread(target=self._run_sequence_thread, args=(plan,), daemon=True)
        self._thread.start()

    def _run_sequence_thread(self, plan: SequencePlan):
        seq_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_dir = os.path.join(plan.save_dir, f"sequence_{seq_ts}")
        os.makedirs(base_dir, exist_ok=True)

        # alles auf 0 setzen (sauberer Start)
        try:
            for ch in self.led.get_all_channels():
                self.led.set_channel_by_name(ch, 0.0)
        except Exception:
            pass

        try:
            total_steps = 0
            for state in plan.ir_states:
                for c in plan.channels:
                    if c.enabled:
                        total_steps += 1
            done = 0

            for ir_state in plan.ir_states:
                # IR state setzen
                self._ui(lambda: self.progress_var.set(f"IR State: {ir_state}"))
                self._set_ir_state(ir_state)

                state_dir = os.path.join(base_dir, f"IR_{ir_state}")
                os.makedirs(state_dir, exist_ok=True)

                for ch_plan in plan.channels:
                    if not ch_plan.enabled:
                        continue

                    done += 1
                    self._ui(lambda n=ch_plan.name, d=done, t=total_steps:
                             self.progress_var.set(f"{d}/{t}: {n}"))

                    # alle LEDs auf 0, dann nur diese setzen
                    self._set_all_leds(0.0)
                    time.sleep(0.05)

                    if ch_plan.mode == "fixed":
                        pwm = float(ch_plan.pwm)
                        self.led.set_channel_by_name(ch_plan.name, pwm)
                        final_pwm = pwm
                    else:
                        final_pwm = self._auto_led_to_target(plan, ch_plan.name, ch_plan.hist_channel)


                    # kurze Settling-Zeit
                    time.sleep(0.15)

                    # Captures
                    ch_dir = os.path.join(state_dir, self._sanitize(ch_plan.name))
                    os.makedirs(ch_dir, exist_ok=True)

                    # Meta speichern
                    meta = {
                        "timestamp": datetime.now().isoformat(),
                        "channel": ch_plan.name,
                        "mode": ch_plan.mode,
                        "final_pwm": final_pwm,
                        "ir_state": ir_state,
                        "hist_channel": plan.hist_channel,
                        "auto_params": {
                            "low_limit": plan.low_limit,
                            "high_limit": plan.high_limit,
                            "low_fraction_target": plan.low_fraction_target,
                            "high_fraction_target": plan.high_fraction_target,
                            "start_step": plan.start_step,
                            "min_step": plan.min_step,
                            "loop_ms": plan.loop_ms,
                            "max_cycles": plan.max_cycles,
                        },
                    }
                    with open(os.path.join(ch_dir, "meta.json"), "w", encoding="utf-8") as f:
                        json.dump(meta, f, indent=2)

                    if ch_plan.jpeg:
                        jpg_path = os.path.join(ch_dir, "capture.jpg")
                        self.stream.capture_still(jpg_path, fmt="jpg")

                    if ch_plan.raw:
                        dng_path = os.path.join(ch_dir, "capture.dng")
                        self.stream.capture_raw_dng(dng_path, both=False)

            self._ui(lambda: self.status_var.set(f"Status: fertig ✅  ({base_dir})"))
            self._ui(lambda: self.progress_var.set(""))

        except Exception as e:
            self._ui(lambda: self.status_var.set("Status: Fehler ❌"))
            self._ui(lambda: self.progress_var.set(str(e)))
        finally:
            # LEDs aus
            try:
                self._set_all_leds(0.0)
            except Exception:
                pass
            self._ui(self._finish_run)

    def _finish_run(self):
        self._running = False
        self.start_btn.config(state="normal")

    def _ui(self, fn):
        # thread-safe UI update
        try:
            self.after(0, fn)
        except Exception:
            pass

    # ---------------- helpers ----------------

    def _sanitize(self, s: str) -> str:
        return "".join(c for c in s if c.isalnum() or c in ("-", "_", ".", " ")).strip().replace(" ", "_")

    def _set_all_leds(self, pwm: float):
        for n in self.led.get_all_channels():
            self.led.set_channel_by_name(n, pwm)

    def _set_ir_state(self, state: str):
        if not self.ir_available or self.ir_filter is None:
            return
        try:
            if state.upper() == "IN":
                self.ir_filter.switch_in()
            else:
                self.ir_filter.switch_out()
        except Exception:
            pass

    def _get_hist_channel_flat(self, frame_np: np.ndarray, sel: str):
        if sel == "R":
            chan = frame_np[:, :, 0]
        elif sel == "G":
            chan = frame_np[:, :, 1]
        elif sel == "B":
            chan = frame_np[:, :, 2]
        else:
            chan = np.mean(frame_np, axis=2)
        return chan.astype(np.uint8, copy=False).ravel()

    def _auto_led_to_target(self, plan: SequencePlan, channel_name: str, hist_channel: str) -> float:
        """
        Headless Auto-LED: regelt nur diesen Kanal, bis innerhalb Toleranz.
        """
        # Start bei 0
        try:
            self.led.set_channel_by_name(channel_name, 0.0)
        except Exception:
            pass

        step = max(plan.start_step, plan.min_step)
        prev_dir = 0
        last_err = None
        stagn = 0

        pwm = 0.0

        for cyc in range(plan.max_cycles):
            frame = self.stream.get_frame()
            if frame is None:
                time.sleep(plan.loop_ms / 1000.0)
                continue

            f = np.array(frame)
            chan = self._get_hist_channel_flat(f, hist_channel)
            hist, _ = np.histogram(chan, bins=256, range=(0, 256))
            total = max(1, chan.size)

            low = hist[: plan.low_limit + 1].sum() / total
            high = hist[255 - plan.high_limit :].sum() / total

            err_dark = max(0.0, low - plan.low_fraction_target)
            err_bright = max(0.0, high - plan.high_fraction_target)
            err = err_dark - err_bright

            if err > plan.eps:
                direction = +1
            elif err < -plan.eps:
                direction = -1
            else:
                direction = 0

            # adapt step
            improved = True
            if last_err is not None:
                improved = (abs(err) < abs(last_err)) or (direction == 0)
                if direction != 0 and prev_dir != 0 and direction != prev_dir:
                    step = max(step / 2.0, plan.min_step)
                elif not improved:
                    stagn += 1
                    if stagn >= 2:
                        step = max(step / 2.0, plan.min_step)
                        stagn = 0

            # update pwm
            if direction == +1:
                pwm = min(100.0, pwm + step)
            elif direction == -1:
                pwm = max(0.0, pwm - step)

            try:
                self.led.set_channel_by_name(channel_name, pwm)
            except Exception:
                pass

            # UI status (non-blocking)
            self._ui(lambda p=pwm, s=step, lo=low, hi=high:
                     self.status_var.set(f"Auto-LED {channel_name}: PWM {p:.1f}% step {s:.2f}% "
                                         f"(low {lo:.1%}, high {hi:.1%})"))

            prev_dir = direction
            last_err = err

            if direction == 0 and step <= plan.min_step:
                break

            time.sleep(plan.loop_ms / 1000.0)

        return float(pwm)

    def _on_close(self):
        if self._running:
            messagebox.showwarning("Sequenz", "Messung läuft – bitte warten bis fertig (oder Prozess stoppen).")
            return
        self.destroy()
