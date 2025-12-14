import json
import os
import sys
import subprocess
from pathlib import Path

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

# Optionaler IR-Filter
try:
    from filter_controller import IRFilterController
except Exception:
    IRFilterController = None


# ---------------- Preset-Verwaltung ----------------

PRESET_DIR = Path.home() / ".config" / "MultispectralCAM" / "camera_presets"
PRESET_DIR.mkdir(parents=True, exist_ok=True)


class PresetManager:
    SCHEMA = 1

    @staticmethod
    def _path(name: str) -> Path:
        safe = "".join(c for c in name if c.isalnum() or c in "-_ .").strip()
        return PRESET_DIR / f"{safe}.json"

    @staticmethod
    def list_presets():
        return sorted(p.stem for p in PRESET_DIR.glob("*.json"))

    @staticmethod
    def save(name: str, data: dict):
        data = dict(data)
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
        return data

    @staticmethod
    def open_folder():
        # rein optional – kann man notfalls ignorieren
        try:
            if sys.platform.startswith("win"):
                os.startfile(PRESET_DIR)  # type: ignore
            elif sys.platform == "darwin":
                subprocess.run(["open", str(PRESET_DIR)])
            else:
                subprocess.run(["xdg-open", str(PRESET_DIR)])
        except Exception as e:
            messagebox.showerror("Presets", f"Ordner konnte nicht geöffnet werden:\n{e}")


# ---------------- Kameraeinstellungs-Dialog ----------------

class CameraSettings(tk.Toplevel):
    """
    Tk-Dialog zur Einstellung der Kamera-Parameter für deinen CameraStream.
    - arbeitet nur über camera_stream.reconfigure(...) + extra_opts
    - keine Picamera2/libcamera-Bindings -> deutlich weniger Segfault-Risiko
    """

    def __init__(self, master, camera_stream):
        super().__init__(master)
        self.title("Kameraeinstellungen – RAW/reproduzierbar")
        self.resizable(False, False)
        self.configure(bg="#2b2b2b")

        self.camera_stream = camera_stream

        # Typische Modi (bitte bei Bedarf anpassen)
        self.modes = [
            (640, 480, 60,  "640×480 @60 (binning)"),
            (1296, 972, 46, "1296×972 @46 (2×2 binning)"),
            (1920, 1080, 30,"1920×1080 @30 (crop)"),
            (2592, 1944, 15,"2592×1944 @15 (full sensor)"),
        ]

        # --- Zustand / Variablen ---
        self.sel_mode = tk.StringVar(value=self.modes[0][3])
        self.shutter_us = tk.IntVar(value=getattr(camera_stream, "shutter", 10000) or 10000)
        self.gain_x     = tk.DoubleVar(value=getattr(camera_stream, "gain", 1.0) or 1.0)
        self.fps        = tk.DoubleVar(value=getattr(camera_stream, "framerate", 30) or 30)

        self.ae_enabled   = tk.BooleanVar(value=False)
        self.awb_enabled  = tk.BooleanVar(value=False)
        self.denoise_mode = tk.StringVar(value="cdn_off")
        self.sharpness    = tk.DoubleVar(value=0.0)
        self.contrast     = tk.DoubleVar(value=1.0)
        self.saturation   = tk.DoubleVar(value=1.0)
        self.flicker      = tk.StringVar(value="off")

        self.awb_r = tk.DoubleVar(value=2.0)
        self.awb_b = tk.DoubleVar(value=1.5)

        # IR-Filter
        self.ir_filter = None
        self.filter_ok = False
        self.filter_state = tk.StringVar(value="unbekannt")
        try:
            if IRFilterController is not None:
                self.ir_filter = IRFilterController()
                self.filter_ok = True
                # falls dein Controller Status liefern kann, ggf. hier setzen:
                # self.filter_state.set("IN" if self.ir_filter.is_in() else "OUT")
        except Exception as e:
            print("[CameraSettings] IRFilterController konnte nicht initiiert werden:", e)
            self.filter_ok = False

        # Versuchen, vorhandene extra_opts aus dem Stream einzulesen
        extra = getattr(self.camera_stream, "extra_opts", {}) or {}
        self._load_extra_opts_into_vars(extra)

        # UI bauen
        self._build_ui()

    # ---------------- Hilfsfunktionen: Extra-Opt. <-> Tk-Variablen ----------------

    def _load_extra_opts_into_vars(self, extra: dict):
        self.denoise_mode.set(extra.get("denoise", self.denoise_mode.get()))
        self.sharpness.set(float(extra.get("sharpness", self.sharpness.get())))
        self.contrast.set(float(extra.get("contrast", self.contrast.get())))
        self.saturation.set(float(extra.get("saturation", self.saturation.get())))
        self.flicker.set(extra.get("flicker", self.flicker.get()))
        self.ae_enabled.set(bool(extra.get("ae", self.ae_enabled.get())))
        self.awb_enabled.set(bool(extra.get("awb", self.awb_enabled.get())))
        awb = extra.get("awbgains", (self.awb_r.get(), self.awb_b.get()))
        self.awb_r.set(float(awb[0]))
        self.awb_b.set(float(awb[1]))

    def _mode_tuple(self):
        label = self.sel_mode.get()
        for w, h, fps_hint, lbl in self.modes:
            if lbl == label:
                return w, h, fps_hint
        return self.modes[0][:3]

    def _collect_extra_opts(self):
        flick = self.flicker.get().lower()
        flick_map = {"off": "off", "50hz": "50Hz", "60hz": "60Hz"}
        flick_val = flick_map.get(flick, "off")
        return {
            "denoise": self.denoise_mode.get(),
            "sharpness": float(self.sharpness.get()),
            "contrast": float(self.contrast.get()),
            "saturation": float(self.saturation.get()),
            "flicker": flick_val,
            "ae": bool(self.ae_enabled.get()),
            "awb": bool(self.awb_enabled.get()),
            "awbgains": (float(self.awb_r.get()), float(self.awb_b.get())),
        }

    def _current_settings_dict(self):
        w, h, fps_hint = self._mode_tuple()
        extra = self._collect_extra_opts()
        return {
            "mode_label": self.sel_mode.get(),
            "width": w,
            "height": h,
            "framerate": float(self.fps.get()),
            "shutter": int(self.shutter_us.get()),
            "gain": float(self.gain_x.get()),
            "extra_opts": extra,
        }

    def _apply_settings_dict(self, s: dict):
        mode_label = s.get("mode_label")
        if mode_label and any(lbl == mode_label for *_rest, lbl in self.modes):
            self.sel_mode.set(mode_label)
        else:
            sw, sh = s.get("width"), s.get("height")
            for w, h, fps_hint, lbl in self.modes:
                if w == sw and h == sh:
                    self.sel_mode.set(lbl)
                    break

        self.fps.set(float(s.get("framerate", self.fps.get())))
        self.shutter_us.set(int(s.get("shutter", self.shutter_us.get())))
        self.gain_x.set(float(s.get("gain", self.gain_x.get())))

        extra = s.get("extra_opts", {})
        self._load_extra_opts_into_vars(extra)

    # ---------------- UI ----------------

    def _build_ui(self):
        pad = dict(padx=10, pady=6)

        # Sensor-Modus
        frm_mode = ttk.LabelFrame(self, text="Sensor-Modus")
        frm_mode.grid(row=0, column=0, sticky="ew", **pad)
        frm_mode.columnconfigure(1, weight=1)
        ttk.Label(frm_mode, text="Auflösung/FPS").grid(row=0, column=0, sticky="w")
        ttk.OptionMenu(frm_mode, self.sel_mode, self.sel_mode.get(), *[m[3] for m in self.modes])\
            .grid(row=0, column=1, sticky="ew", padx=(6, 0))

        # Belichtung
        frm_exp = ttk.LabelFrame(self, text="Belichtung")
        frm_exp.grid(row=1, column=0, sticky="ew", **pad)

        ttk.Label(frm_exp, text="Shutter [µs]").grid(row=0, column=0, sticky="w")
        ttk.Spinbox(frm_exp, from_=50, to=2_000_000, increment=50,
                    textvariable=self.shutter_us, width=10)\
            .grid(row=0, column=1, sticky="w", padx=(6, 6))

        ttk.Label(frm_exp, text="Gain [×]").grid(row=0, column=2, sticky="w")
        ttk.Spinbox(frm_exp, from_=1.0, to=32.0, increment=0.1,
                    textvariable=self.gain_x, width=7)\
            .grid(row=0, column=3, sticky="w", padx=(6, 0))

        ttk.Label(frm_exp, text="FPS").grid(row=0, column=4, sticky="w", padx=(12, 0))
        ttk.Spinbox(frm_exp, from_=1.0, to=90.0, increment=0.5,
                    textvariable=self.fps, width=7)\
            .grid(row=0, column=5, sticky="w", padx=(6, 0))

        # Algorithmen / ISP
        frm_isp = ttk.LabelFrame(self, text="Algorithmen / ISP")
        frm_isp.grid(row=2, column=0, sticky="ew", **pad)

        ttk.Checkbutton(frm_isp, text="Auto Exposure (AE)",
                        variable=self.ae_enabled).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(frm_isp, text="Auto White Balance (AWB)",
                        variable=self.awb_enabled).grid(row=0, column=1, sticky="w", padx=(12, 0))

        ttk.Label(frm_isp, text="Denoise").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.OptionMenu(frm_isp, self.denoise_mode, self.denoise_mode.get(),
                       "cdn_off", "fast", "hq")\
            .grid(row=1, column=1, sticky="w", padx=(6, 0), pady=(8, 0))

        ttk.Label(frm_isp, text="Sharpen").grid(row=1, column=2, sticky="w", padx=(12, 0), pady=(8, 0))
        ttk.Spinbox(frm_isp, from_=0.0, to=2.0, increment=0.1,
                    textvariable=self.sharpness, width=6)\
            .grid(row=1, column=3, sticky="w", padx=(6, 0), pady=(8, 0))

        ttk.Label(frm_isp, text="Contrast").grid(row=2, column=0, sticky="w", pady=(6, 0))
        ttk.Spinbox(frm_isp, from_=0.0, to=2.0, increment=0.1,
                    textvariable=self.contrast, width=6)\
            .grid(row=2, column=1, sticky="w", padx=(6, 0), pady=(6, 0))

        ttk.Label(frm_isp, text="Saturation").grid(row=2, column=2, sticky="w", padx=(12, 0), pady=(6, 0))
        ttk.Spinbox(frm_isp, from_=0.0, to=2.0, increment=0.1,
                    textvariable=self.saturation, width=6)\
            .grid(row=2, column=3, sticky="w", padx=(6, 0), pady=(6, 0))

        ttk.Label(frm_isp, text="Flicker").grid(row=3, column=0, sticky="w", pady=(6, 0))
        ttk.OptionMenu(frm_isp, self.flicker, self.flicker.get(), "off", "50Hz", "60Hz")\
            .grid(row=3, column=1, sticky="w", padx=(6, 0), pady=(6, 0))

        # AWB-Gains
        frm_awb = ttk.LabelFrame(self, text="AWB-Gains (bei AWB aus)")
        frm_awb.grid(row=3, column=0, sticky="ew", **pad)
        ttk.Label(frm_awb, text="R-Gain").grid(row=0, column=0, sticky="w")
        ttk.Spinbox(frm_awb, from_=0.5, to=8.0, increment=0.05,
                    textvariable=self.awb_r, width=7)\
            .grid(row=0, column=1, sticky="w", padx=(6, 0))
        ttk.Label(frm_awb, text="B-Gain").grid(row=0, column=2, sticky="w", padx=(12, 0))
        ttk.Spinbox(frm_awb, from_=0.5, to=8.0, increment=0.05,
                    textvariable=self.awb_b, width=7)\
            .grid(row=0, column=3, sticky="w", padx=(6, 0))

        # Presets
        frm_preset = ttk.LabelFrame(self, text="Presets")
        frm_preset.grid(row=4, column=0, sticky="ew", **pad)
        frm_preset.columnconfigure(1, weight=1)

        self.preset_select = tk.StringVar(value="(Auswählen)")

        ttk.Label(frm_preset, text="Preset:").grid(row=0, column=0, sticky="w")
        self.cmb_preset = ttk.OptionMenu(
            frm_preset,
            self.preset_select,
            self.preset_select.get(),
            *(["(Auswählen)"] + PresetManager.list_presets())
        )
        self.cmb_preset.grid(row=0, column=1, sticky="ew", padx=(6, 6))

        ttk.Button(frm_preset, text="Laden", command=self._load_preset)\
            .grid(row=0, column=2, padx=(0, 4))
        ttk.Button(frm_preset, text="Speichern…", command=self._save_preset_dialog)\
            .grid(row=0, column=3, padx=(0, 4))
        ttk.Button(frm_preset, text="Ordner", command=PresetManager.open_folder)\
            .grid(row=0, column=4)

        # IR-Filter
        frm_filter = ttk.LabelFrame(self, text="IR-Filter")
        frm_filter.grid(row=5, column=0, sticky="ew", **pad)
        ttk.Label(frm_filter, text="Status:").grid(row=0, column=0, sticky="w")
        ttk.Label(frm_filter, textvariable=self.filter_state).grid(row=0, column=1, sticky="w", padx=(6, 12))

        btn_in  = ttk.Button(frm_filter, text="Einschwenken", command=self._filter_in)
        btn_out = ttk.Button(frm_filter, text="Ausschwenken", command=self._filter_out)
        btn_tgl = ttk.Button(frm_filter, text="Toggle", command=self._filter_toggle)
        btn_in.grid(row=0, column=2, padx=(0, 4))
        btn_out.grid(row=0, column=3, padx=(0, 4))
        btn_tgl.grid(row=0, column=4, padx=(0, 0))

        if not self.filter_ok:
            for w in (btn_in, btn_out, btn_tgl):
                w.state(["disabled"])
            self.filter_state.set("nicht verfügbar")

        # Buttons (Anwenden)
        frm_btn = ttk.Frame(self)
        frm_btn.grid(row=6, column=0, sticky="ew", padx=10, pady=(4, 10))

        ttk.Button(frm_btn, text="RAW-optimiert", command=self.apply_raw_optimized)\
            .grid(row=0, column=0, padx=(0, 8))
        ttk.Button(frm_btn, text="Nur Vorschau anwenden",
                   command=lambda: self.apply_settings(preview_only=True))\
            .grid(row=0, column=1, padx=(0, 8))
        ttk.Button(frm_btn, text="Vorschau + Still anwenden",
                   command=lambda: self.apply_settings(preview_only=False))\
            .grid(row=0, column=2, padx=(0, 0))

    # ---------------- Presets ----------------

    def _refresh_preset_menu(self):
        items = ["(Auswählen)"] + PresetManager.list_presets()
        menu = self.cmb_preset["menu"]
        menu.delete(0, "end")
        for it in items:
            menu.add_command(label=it, command=lambda v=it: self.preset_select.set(v))

    def _save_preset_dialog(self):
        name = simpledialog.askstring("Preset speichern", "Name des Presets:", parent=self)
        if not name:
            return
        data = self._current_settings_dict()
        try:
            path = PresetManager.save(name, data)
            self._refresh_preset_menu()
            self.preset_select.set(name)
            messagebox.showinfo("Preset", f"Gespeichert:\n{path}")
        except Exception as e:
            messagebox.showerror("Preset", f"Konnte Preset nicht speichern:\n{e}")

    def _load_preset(self):
        name = self.preset_select.get()
        if not name or name == "(Auswählen)":
            messagebox.showwarning("Preset", "Bitte zuerst ein Preset auswählen.")
            return
        try:
            data = PresetManager.load(name)
            self._apply_settings_dict(data)
        except Exception as e:
            messagebox.showerror("Preset", f"Konnte Preset nicht laden:\n{e}")

    # ---------------- Anwenden ----------------

    def apply_raw_optimized(self):
        # Sinnvolle Defaults für reproduzierbare RAW-Aufnahmen
        self.ae_enabled.set(False)
        self.awb_enabled.set(False)
        self.denoise_mode.set("cdn_off")
        self.sharpness.set(0.0)
        self.contrast.set(1.0)
        self.saturation.set(1.0)
        self.flicker.set("off")
        self.sel_mode.set("2592×1944 @15 (full sensor)")
        messagebox.showinfo("Preset", "RAW-optimierte Einstellungen gesetzt.\n(AE/AWB/ISP aus, Full-Res).")

    def apply_settings(self, preview_only=True):
        w, h, fps_hint = self._mode_tuple()
        extra = self._collect_extra_opts()

        opts = dict(
            width=w,
            height=h,
            framerate=float(self.fps.get()),
            shutter=int(self.shutter_us.get()) if not self.ae_enabled.get() else None,
            gain=float(self.gain_x.get()) if not self.ae_enabled.get() else None,
            extra_opts=extra,
        )

        # an CameraStream -> reconfigure
        try:
            self.camera_stream.reconfigure(**opts)
        except TypeError:
            # Fallback, falls reconfigure extra_opts (noch) nicht kennt
            kw = {k: v for k, v in opts.items() if k in ("width", "height", "framerate", "shutter", "gain")}
            self.camera_stream.reconfigure(**kw)
            setattr(self.camera_stream, "extra_opts", opts.get("extra_opts", {}))
        else:
            # extra_opts im Stream hinterlegen
            if hasattr(self.camera_stream, "set_extra_options"):
                self.camera_stream.set_extra_options(extra)
            else:
                setattr(self.camera_stream, "extra_opts", extra)

        if not preview_only:
            messagebox.showinfo(
                "Hinweis",
                "Einstellungen sind nun für Vorschau aktiv.\n"
                "Stelle sicher, dass deine capture_*-Funktionen extra_opts berücksichtigen."
            )
        print(self.camera_stream.health_check())

        self.destroy()

    # ---------------- IR-Filter ----------------

    def _filter_in(self):
        if not self.ir_filter:
            return
        import threading
        def run():
            try:
                self.ir_filter.switch_in()
                self.filter_state.set("IN")
            except Exception as e:
                print("[IR-Filter] switch_in failed:", e)
        threading.Thread(target=run, daemon=True).start()

    def _filter_out(self):
        if not self.ir_filter:
            return
        import threading
        def run():
            try:
                self.ir_filter.switch_out()
                self.filter_state.set("OUT")
            except Exception as e:
                print("[IR-Filter] switch_out failed:", e)
        threading.Thread(target=run, daemon=True).start()

    def _filter_toggle(self):
        if not self.ir_filter:
            return
        target = "OUT" if self.filter_state.get().upper() == "IN" else "IN"
        if target == "IN":
            self._filter_in()
        else:
            self._filter_out()
