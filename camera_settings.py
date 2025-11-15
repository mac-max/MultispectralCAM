import tkinter as tk
import threading
from tkinter import ttk, messagebox
try:
    from filter_controller import IRFilterController
except Exception:
    IRFilterController = None
import json, os, sys, webbrowser
from pathlib import Path

PRESET_DIR = Path.home() / ".config" / "MultispectralCAM" / "camera_presets"
PRESET_DIR.mkdir(parents=True, exist_ok=True)

class PresetManager:
    SCHEMA = 1

    @staticmethod
    def _path(name: str) -> Path:
        safe = "".join(c for c in name if c.isalnum() or c in "-_ .").strip()
        return PRESET_DIR / f"{safe}.json"

    @staticmethod
    def list_presets() -> list[str]:
        return sorted(p.stem for p in PRESET_DIR.glob("*.json"))

    @staticmethod
    def save(name: str, data: dict):
        data = dict(data)  # copy
        data["_schema"] = PresetManager.SCHEMA
        path = PresetManager._path(name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return path

    @staticmethod
    def load(name: str) -> dict:
        path = PresetManager._path(name)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # schema handling could go here if needed
        return data

    @staticmethod
    def open_folder():
        if sys.platform.startswith("win"):
            os.startfile(PRESET_DIR)  # type: ignore
        elif sys.platform == "darwin":
            subprocess.run(["open", str(PRESET_DIR)])
        else:
            subprocess.run(["xdg-open", str(PRESET_DIR)])


class CameraSettings(tk.Toplevel):
    """
    Granularer Einstell-Dialog für reproduzierbare RAW-Aufnahmen.
    Erwartet: camera_stream mit .reconfigure(**kwargs) und (optional) .capture_* nutzt extra_opts.
    """
    def __init__(self, master, camera_stream):
        super().__init__(master)
        self.title("Kameraeinstellungen – RAW/reproduzierbar")
        self.resizable(False, False)
        # IR-Filter (optional)
        self.ir_filter = None
        self.filter_state = tk.StringVar(value="unbekannt")
        self.filter_ok = False
        try:
            if IRFilterController is not None:
                self.ir_filter = IRFilterController()
                self.filter_ok = True
                # Wenn dein Controller einen Status liefern kann, hier setzen:
                # z.B. self.filter_state.set("IN" if self.ir_filter.is_in() else "OUT")
                # Falls nicht verfügbar, lassen wir "unbekannt".
        except Exception as e:
            print("[CameraSettings] IRFilterController konnte nicht initiiert werden:", e)
            self.filter_ok = False

        self.camera_stream = camera_stream

        # --- Presets für Sensor-Modi (OV5647/IMX219 typische Modi; passe bei Bedarf an) ---
        # (width, height, fps_hint, label)
        self.modes = [
            (640, 480, 60,  "640×480 @60 (binning)"),
            (1296, 972, 46, "1296×972 @46 (2×2 binning)"),
            (1920, 1080, 30,"1920×1080 @30 (crop)"),
            (2592, 1944, 15,"2592×1944 @15 (full sensor)"),
        ]

        # --- Tk-States ---
        self.sel_mode = tk.StringVar(value=self.modes[0][3])
        self.shutter_us = tk.IntVar(value=getattr(camera_stream, "shutter", 10000) or 10000)
        self.gain_x     = tk.DoubleVar(value=getattr(camera_stream, "gain", 1.0) or 1.0)
        self.fps        = tk.DoubleVar(value=getattr(camera_stream, "framerate", 30) or 30)

        # ISP/Algorithmen
        self.ae_enabled   = tk.BooleanVar(value=False)
        self.awb_enabled  = tk.BooleanVar(value=False)
        self.denoise_mode = tk.StringVar(value="cdn_off")   # cdn_off|fast|hq (abhängig libcamera)
        self.sharpness    = tk.DoubleVar(value=0.0)
        self.contrast     = tk.DoubleVar(value=1.0)
        self.saturation   = tk.DoubleVar(value=1.0)
        self.flicker      = tk.StringVar(value="off")       # off|50Hz|60Hz

        # AWB-Gains (nur wirksam bei AWB off)
        self.awb_r = tk.DoubleVar(value=2.0)
        self.awb_b = tk.DoubleVar(value=1.5)

        # IR-Filter
        frm_filter = ttk.LabelFrame(self, text="IR-Filter")
        frm_filter.grid(row=5, column=0, sticky="ew", padx=10, pady=6)
        frm_filter.columnconfigure(3, weight=1)

        ttk.Label(frm_filter, text="Status:").grid(row=0, column=0, sticky="w")
        self.lbl_filter = ttk.Label(frm_filter, textvariable=self.filter_state)
        self.lbl_filter.grid(row=0, column=1, sticky="w", padx=(6, 12))

        btn_in = ttk.Button(frm_filter, text="Einschwenken", command=self._filter_in)
        btn_out = ttk.Button(frm_filter, text="Ausschwenken", command=self._filter_out)
        btn_tgl = ttk.Button(frm_filter, text="Toggle", command=self._filter_toggle)
        btn_in.grid(row=0, column=2, padx=(0, 6))
        btn_out.grid(row=0, column=3, padx=(0, 6), sticky="w")
        btn_tgl.grid(row=0, column=4, padx=(0, 0), sticky="w")

        # Buttons ggf. deaktivieren, wenn kein Controller
        if not self.filter_ok:
            for w in (btn_in, btn_out, btn_tgl):
                w.state(["disabled"])
            self.filter_state.set("nicht verfügbar")

        # GUI
        self._build_ui()

    def _current_settings_dict(self) -> dict:
        """Alles, was wir reproduzierbar machen wollen, als dict exportieren."""
        w, h, fps_hint = self._mode_tuple()
        extra = {
            "denoise": self.denoise_mode.get(),
            "sharpness": float(self.sharpness.get()),
            "contrast": float(self.contrast.get()),
            "saturation": float(self.saturation.get()),
            "flicker": self.flicker.get(),
            "ae": bool(self.ae_enabled.get()),
            "awb": bool(self.awb_enabled.get()),
            "awbgains": (float(self.awb_r.get()), float(self.awb_b.get())),
        }
        return {
            "mode_label": self.sel_mode.get(),
            "width": w, "height": h,
            "framerate": float(self.fps.get()),
            "shutter": int(self.shutter_us.get()),
            "gain": float(self.gain_x.get()),
            "extra_opts": extra,
        }

    def _apply_settings_dict(self, s: dict):
        """Preset → GUI Felder setzen (mit sinnvollen Defaults)."""
        # Modus (Label bevorzugt; sonst width/height matchen)
        mode_label = s.get("mode_label")
        if mode_label and any(lbl == mode_label for *_, lbl in self.modes):
            self.sel_mode.set(mode_label)
        else:
            # versuche anhand width/height
            sw, sh = s.get("width"), s.get("height")
            for w, h, f, lbl in self.modes:
                if w == sw and h == sh:
                    self.sel_mode.set(lbl);
                    break

        self.fps.set(float(s.get("framerate", self.fps.get())))
        self.shutter_us.set(int(s.get("shutter", self.shutter_us.get())))
        self.gain_x.set(float(s.get("gain", self.gain_x.get())))

        extra = s.get("extra_opts", {})
        self.denoise_mode.set(extra.get("denoise", self.denoise_mode.get()))
        self.sharpness.set(float(extra.get("sharpness", self.sharpness.get())))
        self.contrast.set(float(extra.get("contrast", self.contrast.get())))
        self.saturation.set(float(extra.get("saturation", self.saturation.get())))
        self.flicker.set(extra.get("flicker", self.flicker.get()))
        self.ae_enabled.set(bool(extra.get("ae", self.ae_enabled.get())))
        self.awb_enabled.set(bool(extra.get("awb", self.awb_enabled.get())))
        awb = extra.get("awbgains", (self.awb_r.get(), self.awb_b.get()))
        self.awb_r.set(float(awb[0]));
        self.awb_b.set(float(awb[1]))

    def _save_preset_dialog(self):
        import tkinter.simpledialog as sd
        name = sd.askstring("Preset speichern", "Name des Presets:", parent=self)
        if not name:
            return
        data = self._current_settings_dict()
        try:
            path = PresetManager.save(name, data)
            self._refresh_presets()
            self.preset_select.set(name)
            messagebox.showinfo("Preset", f"Gespeichert:\n{path}")
        except Exception as e:
            messagebox.showerror("Fehler", f"Konnte Preset nicht speichern:\n{e}")

    def _load_preset(self):
        name = self.preset_select.get()
        if not name or name == "(Auswählen)":
            messagebox.showwarning("Hinweis", "Bitte zuerst ein Preset auswählen.")
            return
        try:
            data = PresetManager.load(name)
            self._apply_settings_dict(data)
        except Exception as e:
            messagebox.showerror("Fehler", f"Konnte Preset nicht laden:\n{e}")

    # ---------------- UI ----------------
    def _build_ui(self):
        pad = dict(padx=10, pady=6)

        # Sensor-Modus
        frm_mode = ttk.LabelFrame(self, text="Sensor-Modus")
        frm_mode.grid(row=0, column=0, sticky="ew", **pad)
        ttk.Label(frm_mode, text="Auflösung/FPS").grid(row=0, column=0, sticky="w")
        om = ttk.OptionMenu(frm_mode, self.sel_mode, self.sel_mode.get(), *[m[3] for m in self.modes])
        om.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        frm_mode.columnconfigure(1, weight=1)

        # Belichtung/Gain/FPS
        frm_exp = ttk.LabelFrame(self, text="Belichtung")
        frm_exp.grid(row=1, column=0, sticky="ew", **pad)
        ttk.Label(frm_exp, text="Shutter [µs]").grid(row=0, column=0, sticky="w")
        ttk.Spinbox(frm_exp, from_=50, to=2_000_000, increment=50, textvariable=self.shutter_us, width=10)\
            .grid(row=0, column=1, sticky="w", padx=(8,0))

        ttk.Label(frm_exp, text="Gain [×]").grid(row=0, column=2, sticky="w", padx=(12,0))
        ttk.Spinbox(frm_exp, from_=1.0, to=32.0, increment=0.1, textvariable=self.gain_x, width=7)\
            .grid(row=0, column=3, sticky="w", padx=(8,0))

        ttk.Label(frm_exp, text="FPS").grid(row=0, column=4, sticky="w", padx=(12,0))
        ttk.Spinbox(frm_exp, from_=1.0, to=90.0, increment=0.5, textvariable=self.fps, width=6)\
            .grid(row=0, column=5, sticky="w", padx=(8,0))

        # Algorithmik/ISP
        frm_isp = ttk.LabelFrame(self, text="Algorithmen / ISP")
        frm_isp.grid(row=2, column=0, sticky="ew", **pad)
        ttk.Checkbutton(frm_isp, text="Auto Exposure (AE) aktiv", variable=self.ae_enabled)\
            .grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(frm_isp, text="Auto White Balance (AWB) aktiv", variable=self.awb_enabled)\
            .grid(row=0, column=1, sticky="w", padx=(12,0))
        ttk.Label(frm_isp, text="Denoise").grid(row=1, column=0, sticky="w", pady=(8,0))
        ttk.OptionMenu(frm_isp, self.denoise_mode, self.denoise_mode.get(), "cdn_off", "fast", "hq")\
            .grid(row=1, column=1, sticky="w", padx=(12,0), pady=(8,0))
        ttk.Label(frm_isp, text="Sharpen").grid(row=1, column=2, sticky="w", padx=(12,0), pady=(8,0))
        ttk.Spinbox(frm_isp, from_=0.0, to=2.0, increment=0.1, textvariable=self.sharpness, width=6)\
            .grid(row=1, column=3, sticky="w", padx=(6,0), pady=(8,0))
        ttk.Label(frm_isp, text="Contrast").grid(row=2, column=0, sticky="w", pady=(6,0))
        ttk.Spinbox(frm_isp, from_=0.0, to=2.0, increment=0.1, textvariable=self.contrast, width=6)\
            .grid(row=2, column=1, sticky="w", padx=(12,0), pady=(6,0))
        ttk.Label(frm_isp, text="Saturation").grid(row=2, column=2, sticky="w", padx=(12,0), pady=(6,0))
        ttk.Spinbox(frm_isp, from_=0.0, to=2.0, increment=0.1, textvariable=self.saturation, width=6)\
            .grid(row=2, column=3, sticky="w", padx=(6,0), pady=(6,0))
        ttk.Label(frm_isp, text="Flicker").grid(row=3, column=0, sticky="w", pady=(6,0))
        ttk.OptionMenu(frm_isp, self.flicker, self.flicker.get(), "off", "50Hz", "60Hz")\
            .grid(row=3, column=1, sticky="w", padx=(12,0), pady=(6,0))

        # AWB Gains (nur relevant bei AWB off)
        frm_awb = ttk.LabelFrame(self, text="AWB-Gains (wirksam nur bei AWB aus)")
        frm_awb.grid(row=3, column=0, sticky="ew", **pad)
        ttk.Label(frm_awb, text="R-Gain").grid(row=0, column=0, sticky="w")
        ttk.Spinbox(frm_awb, from_=0.5, to=8.0, increment=0.05, textvariable=self.awb_r, width=7)\
            .grid(row=0, column=1, sticky="w", padx=(8,0))
        ttk.Label(frm_awb, text="B-Gain").grid(row=0, column=2, sticky="w", padx=(12,0))
        ttk.Spinbox(frm_awb, from_=0.5, to=8.0, increment=0.05, textvariable=self.awb_b, width=7)\
            .grid(row=0, column=3, sticky="w", padx=(8,0))

        # Presets
        frm_preset = ttk.LabelFrame(self, text="Presets")
        frm_preset.grid(row=4, column=0, sticky="ew", padx=10, pady=(2, 6))
        frm_preset.columnconfigure(1, weight=1)

        self.preset_name = tk.StringVar(value="")
        self.preset_select = tk.StringVar(value="(Auswählen)")


        def _refresh_presets():
            items = ["(Auswählen)"] + PresetManager.list_presets()
            menu = self.cmb_preset["menu"]
            menu.delete(0, "end")
            for it in items:
                menu.add_command(label=it, command=lambda v=it: self.preset_select.set(v))

        ttk.Label(frm_preset, text="Preset:").grid(row=0, column=0, sticky="w")
        self.cmb_preset = ttk.OptionMenu(frm_preset, self.preset_select, self.preset_select.get(),
                                         *(["(Auswählen)"] + PresetManager.list_presets()))
        self.cmb_preset.grid(row=0, column=1, sticky="ew", padx=(6, 6))

        ttk.Button(frm_preset, text="Laden", command=self._load_preset).grid(row=0, column=2, padx=(0, 4))
        ttk.Button(frm_preset, text="Speichern…", command=self._save_preset_dialog).grid(row=0, column=3, padx=(0, 4))
        ttk.Button(frm_preset, text="Ordner", command=PresetManager.open_folder).grid(row=0, column=4)

        # lokale Methode verfügbar machen
        self._refresh_presets = _refresh_presets

        # Buttons
        frm_btn = ttk.Frame(self)
        frm_btn.grid(row=5, column=0, sticky="ew", **pad)
        ttk.Button(frm_btn, text="RAW-optimiert anwenden", command=self.apply_raw_optimized)\
            .grid(row=0, column=0, padx=(0,8))
        ttk.Button(frm_btn, text="Nur Vorschau anwenden", command=lambda: self.apply_settings(preview_only=True))\
            .grid(row=0, column=1, padx=(0,8))
        ttk.Button(frm_btn, text="Vorschau + Still anwenden", command=lambda: self.apply_settings(preview_only=False))\
            .grid(row=0, column=2)


    # ---------------- Helpers ----------------
    def _mode_tuple(self):
        label = self.sel_mode.get()
        for w,h,f,lbl in self.modes:
            if lbl == label:
                return w, h, f
        return self.modes[0][0], self.modes[0][1], self.modes[0][2]

    def _collect_opts(self):
        """Sammelt Optionen für CameraStream.reconfigure(...)."""
        width, height, fps_hint = self._mode_tuple()
        # Map Flicker
        flick = self.flicker.get().lower()
        flick_map = {"off": "off", "50hz": "50Hz", "60hz": "60Hz"}
        flick_val = flick_map.get(flick, "off")

        extra_opts = {
            # libcamera-vid/still common flags (erweitere build_command entsprechend!)
            "denoise": self.denoise_mode.get(),       # -> --denoise cdn_off|fast|hq
            "sharpness": float(self.sharpness.get()), # -> --sharpness X
            "contrast": float(self.contrast.get()),   # -> --contrast X
            "saturation": float(self.saturation.get()),# -> --saturation X
            "flicker": flick_val,                     # -> --flicker off|50Hz|60Hz
            "ae": bool(self.ae_enabled.get()),        # -> --ae on/off (simuliert: AE aus = set shutter/gain)
            "awb": bool(self.awb_enabled.get()),      # -> --awb off + --awbgains R B wenn False
            "awbgains": (float(self.awb_r.get()), float(self.awb_b.get())),
        }

        opts = dict(
            width=width,
            height=height,
            framerate=float(self.fps.get()),
            shutter=int(self.shutter_us.get()) if not self.ae_enabled.get() else None,
            gain=float(self.gain_x.get()) if not self.ae_enabled.get() else None,
            extra_opts=extra_opts,
        )
        return opts

    # ---------------- Actions ----------------
    def apply_raw_optimized(self):
        """
        Setzt sinnvolle Defaults für echte RAW-Aufnahmen (reproduzierbar):
        - AE/AWB aus, feste awbgains
        - Denoise aus, Schärfung 0, Kontrast/Sättigung neutral
        - Flicker aus
        - Full-Res Sensor-Modus, moderate FPS
        """
        self.ae_enabled.set(False)
        self.awb_enabled.set(False)
        self.denoise_mode.set("cdn_off")
        self.sharpness.set(0.0)
        self.contrast.set(1.0)
        self.saturation.set(1.0)
        self.flicker.set("off")
        self.sel_mode.set("2592×1944 @15 (full sensor)")
        messagebox.showinfo("Preset", "RAW-optimierte Einstellungen gesetzt (AWB/AE/ISP aus, Full-Res).")

    def apply_settings(self, preview_only=True):
        opts = self._collect_opts()

        # An CameraStream übergeben
        try:
            self.camera_stream.reconfigure(**opts)
        except TypeError:
            # Fallback für ältere reconfigure-Signaturen:
            kw = {k: v for k, v in opts.items() if k in ("width","height","framerate","shutter","gain")}
            self.camera_stream.reconfigure(**kw)
            # extra_opts wird ggf. von capture-Funktionen separat ausgewertet

        # Optional: dem Stream die extra_opts merken, damit capture_* das übernimmt
        if hasattr(self.camera_stream, "set_extra_options"):
            self.camera_stream.set_extra_options(opts.get("extra_opts", {}))
        else:
            # einfache Ablage (wenn du willst, implementiere set_extra_options in CameraStream)
            setattr(self.camera_stream, "extra_opts", opts.get("extra_opts", {}))

        if not preview_only:
            messagebox.showinfo("Hinweis", "Einstellungen sind für Vorschau aktiv. "
                                "Stelle sicher, dass deine capture_*-Routinen extra_opts berücksichtigen.")



    def _filter_in(self):
        if not self.ir_filter: return

        def run():
            try:
                self.ir_filter.switch_in()
                self.filter_state.set("IN")
            except Exception as e:
                print("[IR-Filter] switch_in failed:", e)

        threading.Thread(target=run, daemon=True).start()

    def _filter_out(self):
        if not self.ir_filter: return

        def run():
            try:
                self.ir_filter.switch_out()
                self.filter_state.set("OUT")
            except Exception as e:
                print("[IR-Filter] switch_out failed:", e)

        threading.Thread(target=run, daemon=True).start()

    def _filter_toggle(self):
        # Wenn dein Controller keine echte Toggle-Funktion hat: Status heuristisch wechseln
        if not self.ir_filter: return
        target = "OUT" if self.filter_state.get().upper() == "IN" else "IN"
        if target == "IN":
            self._filter_in()
        else:
            self._filter_out()

# import tkinter as tk
# from tkinter import ttk
# from filter_controller import IRFilterController
#
# class CameraSettings(tk.Toplevel):
#     def __init__(self, master, camera_stream):
#         super().__init__(master)
#         self.title("Kameraeinstellungen")
#         self.camera_stream = camera_stream
#
#         # === IR-Filtersteuerung initialisieren ===
#         self.ir_filter = IRFilterController()
#
#         self.res_options = {
#             "640x480 @59fps": (640, 480, 59),
#             "1296x972 @46fps": (1296, 972, 46),
#             "1920x1080 @32fps": (1920, 1080, 32),
#             "2592x1944 @15fps": (2592, 1944, 15)
#         }
#
#         self.selected_res = tk.StringVar(value="640x480 @59fps")
#         self.shutter_var = tk.IntVar(value=10000)  # µs
#         self.gain_var = tk.DoubleVar(value=1.0)
#
#         self.build_ui()
#
#     def build_ui(self):
#         frame = ttk.Frame(self)
#         frame.pack(padx=10, pady=10, fill="x")
#
#         # Auflösung
#         ttk.Label(frame, text="Auflösung & FPS:").pack(anchor="w")
#         res_menu = ttk.OptionMenu(frame, self.selected_res, self.selected_res.get(), *self.res_options.keys())
#         res_menu.pack(fill="x", pady=(0, 10))
#
#         # Belichtungszeit
#         ttk.Label(frame, text="Belichtungszeit [µs]:").pack(anchor="w")
#         shutter_slider = ttk.Scale(frame, from_=10, to=100000, variable=self.shutter_var, orient="horizontal")
#         shutter_slider.pack(fill="x", pady=(0, 10))
#         ttk.Label(frame, textvariable=self.shutter_var).pack(anchor="e")
#
#         # Gain
#         ttk.Label(frame, text="Gain:").pack(anchor="w")
#         gain_slider = ttk.Scale(frame, from_=1.0, to=16.0, variable=self.gain_var, orient="horizontal")
#         gain_slider.pack(fill="x", pady=(0, 10))
#         ttk.Label(frame, textvariable=self.gain_var).pack(anchor="e")
#
#         # IR-Filtersteuerung
#         ttk.Label(frame, text="IR-Filter:").pack(anchor="w", pady=(10, 0))
#         btn_frame = ttk.Frame(frame)
#         btn_frame.pack(fill="x", pady=(0, 10))
#
#         ttk.Button(btn_frame, text="Einschwenken", command=self.switch_filter_in).pack(side="left", expand=True,
#                                                                                        fill="x", padx=(0, 5))
#         ttk.Button(btn_frame, text="Ausschwenken", command=self.switch_filter_out).pack(side="left", expand=True,
#                                                                                         fill="x", padx=(5, 0))
#
#         # Anwenden-Button
#         ttk.Button(frame, text="Anwenden", command=self.apply_settings).pack(pady=(10, 0))
#
#     def switch_filter_in(self):
#         print("[INFO] IR-Filter wird eingeschwenkt.")
#         self.ir_filter.switch_in()
#
#     def switch_filter_out(self):
#         print("[INFO] IR-Filter wird ausgeschwenkt.")
#         self.ir_filter.switch_out()
#
#     def apply_settings(self):
#         res_label = self.selected_res.get()
#         width, height, framerate = self.res_options[res_label]
#         shutter = self.shutter_var.get()
#         gain = round(self.gain_var.get(), 2)
#
#         print(f"[INFO] Neue Kameraeinstellungen: {width}x{height}, {framerate}fps, shutter={shutter}, gain={gain}")
#         self.camera_stream.reconfigure(width=width, height=height, framerate=framerate, shutter=shutter, gain=gain)
#         self.destroy()
