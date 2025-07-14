import tkinter as tk
from tkinter import ttk
from filter_controller import IRFilterController

class CameraSettings(tk.Toplevel):
    def __init__(self, master, camera_stream):
        super().__init__(master)
        self.title("Kameraeinstellungen")
        self.camera_stream = camera_stream

        self.res_options = {
            "640x480 @59fps": (640, 480, 59),
            "1296x972 @46fps": (1296, 972, 46),
            "1920x1080 @32fps": (1920, 1080, 32),
            "2592x1944 @15fps": (2592, 1944, 15)
        }

        self.selected_res = tk.StringVar(value="640x480 @59fps")
        self.shutter_var = tk.IntVar(value=10000)  # µs
        self.gain_var = tk.DoubleVar(value=1.0)

        self.build_ui()

    def build_ui(self):
        frame = ttk.Frame(self)
        frame.pack(padx=10, pady=10, fill="x")

        # Auflösung
        ttk.Label(frame, text="Auflösung & FPS:").pack(anchor="w")
        res_menu = ttk.OptionMenu(frame, self.selected_res, self.selected_res.get(), *self.res_options.keys())
        res_menu.pack(fill="x", pady=(0, 10))

        # Belichtungszeit
        ttk.Label(frame, text="Belichtungszeit [µs]:").pack(anchor="w")
        shutter_slider = ttk.Scale(frame, from_=100, to=30000, variable=self.shutter_var, orient="horizontal")
        shutter_slider.pack(fill="x", pady=(0, 10))
        ttk.Label(frame, textvariable=self.shutter_var).pack(anchor="e")

        # Gain
        ttk.Label(frame, text="Gain:").pack(anchor="w")
        gain_slider = ttk.Scale(frame, from_=1.0, to=16.0, variable=self.gain_var, orient="horizontal")
        gain_slider.pack(fill="x", pady=(0, 10))
        ttk.Label(frame, textvariable=self.gain_var).pack(anchor="e")

        # IR-Filtersteuerung
        ttk.Label(frame, text="IR-Filter:").pack(anchor="w", pady=(10, 0))
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill="x", pady=(0, 10))

        ttk.Button(btn_frame, text="Einschwenken", command=self.switch_filter_in).pack(side="left", expand=True,
                                                                                       fill="x", padx=(0, 5))
        ttk.Button(btn_frame, text="Ausschwenken", command=self.switch_filter_out).pack(side="left", expand=True,
                                                                                        fill="x", padx=(5, 0))

        # Anwenden-Button
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
        self.camera_stream.reconfigure(width=width, height=height, framerate=framerate, shutter=shutter, gain=gain)
        self.destroy()
