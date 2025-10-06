import tkinter as tk
from tkinter import ttk
import board
import busio
from adafruit_as7341 import AS7341, Gain
from adafruit_bus_device.i2c_device import I2CDevice
import threading
import time

class SensorMonitor(tk.Toplevel):
    def __init__(self, master=None):
        super().__init__(master)
        self.title("AS7341 Spektralsensor")
        self.geometry("460x800")

        try:
            i2c = busio.I2C(board.SCL, board.SDA)
            self.sensor = AS7341(i2c)
            self.device = I2CDevice(i2c, 0x39)
            self.sensor.gain = Gain.GAIN_256X
        except Exception as e:
            ttk.Label(self, text=f"[Fehler beim Sensorinit: {e}]").pack()
            return

        self.light_on = False
        self.ir_filter_on = False
        self.running = True
        self.bars = {}

        self.build_ui()
        threading.Thread(target=self.update_loop, daemon=True).start()

    def build_ui(self):
        frame = ttk.Frame(self)
        frame.pack(padx=20, pady=10, fill="x")

        # Kanäle (Slot 0 und Slot 1)
        self.channels = [
            ("F1 415 nm", "slot0", lambda: self.sensor.channel_415nm),
            ("F2 445 nm", "slot0", lambda: self.sensor.channel_445nm),
            ("F3 480 nm", "slot0", lambda: self.sensor.channel_480nm),
            ("F4 515 nm", "slot0", lambda: self.sensor.channel_515nm),
            ("Clear 0",   "slot0", lambda: self.sensor.clear_channel),
            ("NIR 0",     "slot0", lambda: self.sensor.nir_channel),

            ("F5 555 nm", "slot1", lambda: self.sensor.channel_555nm),
            ("F6 590 nm", "slot1", lambda: self.sensor.channel_590nm),
            ("F7 630 nm", "slot1", lambda: self.sensor.channel_630nm),
            ("F8 680 nm", "slot1", lambda: self.sensor.channel_680nm),
            ("Clear 1",   "slot1", lambda: self.sensor.clear_channel),
            ("NIR 1",     "slot1", lambda: self.sensor.nir_channel),
        ]

        for label_text, slot, _ in self.channels:
            row = ttk.Frame(frame)
            row.pack(fill='x', pady=2)
            ttk.Label(row, text=label_text, width=12).pack(side='left')
            bar = ttk.Progressbar(row, orient='horizontal', length=250, mode='determinate', maximum=60000)
            bar.pack(side='left', padx=5)
            label = ttk.Label(row, text="0")
            label.pack(side='right')
            self.bars[label_text] = (bar, label)

        self.flicker_label = ttk.Label(self, text="Flicker: wird erkannt ...", font=("Arial", 10, "bold"))
        self.flicker_label.pack(pady=10)

        self.led_btn = ttk.Button(self, text="Sensor-LED EIN", command=self.toggle_light)
        self.led_btn.pack(pady=5)

        self.ir_btn = ttk.Button(self, text="IR-Filter AKTIVIEREN", command=self.toggle_ir_filter)
        self.ir_btn.pack(pady=5)

        ttk.Label(self, text="Gain wählen:").pack(pady=(15, 0))
        self.gain_options = {
            "0.5x": Gain.GAIN_0_5X,
            "1x": Gain.GAIN_1X,
            "4x": Gain.GAIN_4X,
            "16x": Gain.GAIN_16X,
            "64x": Gain.GAIN_64X,
            "128x": Gain.GAIN_128X,
            "256x": Gain.GAIN_256X
        }
        self.selected_gain = tk.StringVar(value="256x")
        gain_menu = ttk.OptionMenu(self, self.selected_gain, self.selected_gain.get(), *self.gain_options.keys(), command=self.set_gain)
        gain_menu.pack()

    def toggle_light(self):
        self.light_on = not self.light_on
        self.sensor.led_current = 20
        self.sensor.led = self.light_on
        self.led_btn.config(text="Sensor-LED AUS" if self.light_on else "Sensor-LED EIN")

    def toggle_ir_filter(self):
        self.ir_filter_on = not self.ir_filter_on
        self.set_gpio_as_output(self.ir_filter_on)
        self.ir_btn.config(text="IR-Filter DEAKTIVIEREN" if self.ir_filter_on else "IR-Filter AKTIVIEREN")

    def set_gpio_as_output(self, high=True):
        try:
            value = 0b10 | (1 if high else 0)
            with self.device as i2c:
                i2c.write(bytes([0x70, value]))
        except Exception as e:
            print(f"[Fehler] IR-Filter GPIO nicht gesetzt: {e}")

    def set_gain(self, label):
        try:
            gain_value = self.gain_options[label]
            self.sensor.gain = gain_value
            print(f"[INFO] Gain gesetzt auf {label}")
        except Exception as e:
            print(f"[Fehler] Gain konnte nicht gesetzt werden: {e}")

    def flicker_text(self, code):
        return {
            0: "Kein Flimmern erkannt",
            1: "50 Hz erkannt",
            2: "60 Hz erkannt",
            3: "100 Hz erkannt",
            4: "120 Hz erkannt",
            255: "Fehler / keine Messung"
        }.get(code, f"Unbekannt ({code})")

    def set_smux_slot0(self):
        smux = [
            0x00, 0x00, 0b00101100,  # F1-F4
            0b00000011, 0x00, 0x00,
            0x00, 0x00, 0x00, 0x00,
            0x00, 0x00
        ]
        self.device.write(bytes([0x00, 0x30]))
        for i in range(12):
            self.device.write(bytes([0x31 + i, smux[i]]))
        self.device.write(bytes([0x00, 0x00]))

    def set_smux_slot1(self):
        smux = [
            0x00, 0x00, 0x00,
            0b00000011, 0x00, 0b00101100,  # F5-F8
            0x00, 0x00, 0x00, 0x00,
            0x00, 0x00
        ]
        self.device.write(bytes([0x00, 0x30]))
        for i in range(12):
            self.device.write(bytes([0x31 + i, smux[i]]))
        self.device.write(bytes([0x00, 0x00]))

    def start_measurement(self):
        self.device.write(bytes([0x80, 0x10]))  # ENABLE: PON + FDC
        while True:
            result = bytearray(1)
            self.device.write_then_readinto(bytes([0x91]), result)
            if result[0] & 0x40:
                break

    def update_loop(self):
        while self.running:
            try:
                self.set_smux_slot0()
                self.start_measurement()
                for label_text, slot, getter in self.channels:
                    if slot == "slot0":
                        val = getter()
                        self.bars[label_text][0]['value'] = val
                        self.bars[label_text][1]['text'] = str(val)

                self.set_smux_slot1()
                self.start_measurement()
                for label_text, slot, getter in self.channels:
                    if slot == "slot1":
                        val = getter()
                        self.bars[label_text][0]['value'] = val
                        self.bars[label_text][1]['text'] = str(val)

                f = self.sensor.flicker_detected
                self.flicker_label['text'] = "Flicker: " + self.flicker_text(f)

            except Exception as e:
                print("Fehler beim Sensorlesen:", e)

            time.sleep(0.5)

    def destroy(self):
        self.running = False
        self.set_gpio_as_output(False)
        super().destroy()
