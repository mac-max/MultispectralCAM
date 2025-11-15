import tkinter as tk
from tkinter import ttk, messagebox

class CameraSettings(tk.Toplevel):
    """
    Granularer Einstell-Dialog für reproduzierbare RAW-Aufnahmen.
    Erwartet: camera_stream mit .reconfigure(**kwargs) und (optional) .capture_* nutzt extra_opts.
    """
    def __init__(self, master, camera_stream):
        super().__init__(master)
        self.title("Kameraeinstellungen – RAW/reproduzierbar")
        self.resizable(False, False)
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

        # GUI
        self._build_ui()

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

        # Buttons
        frm_btn = ttk.Frame(self)
        frm_btn.grid(row=4, column=0, sticky="ew", **pad)
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
