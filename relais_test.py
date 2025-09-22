import tkinter as tk
from tkinter import ttk
import pigpio

class GPIORelayGUI(tk.Tk):
    def __init__(self, pins):
        super().__init__()
        self.title("GPIO-Relaissteuerung")
        self.geometry("400x250")

        self.pi = pigpio.pi()
        if not self.pi.connected:
            raise RuntimeError("pigpio daemon is not running")

        self.pins = pins
        self.labels = {}

        self.setup_gpio()
        self.build_ui()
        self.update_pin_states()

    def setup_gpio(self):
        for pin in self.pins:
            self.pi.set_mode(pin, pigpio.OUTPUT)
            self.pi.set_pull_up_down(pin, pigpio.PUD_DOWN)  # stabiler LOW-Zustand
            self.pi.write(pin, 0)  # Init auf LOW

    def build_ui(self):
        for idx, pin in enumerate(self.pins):
            frame = ttk.LabelFrame(self, text=f"GPIO {pin}")
            frame.grid(row=idx, column=0, padx=10, pady=5, sticky="ew")

            on_btn = ttk.Button(frame, text="EIN (HIGH)", command=lambda p=pin: self.set_pin(p, 1))
            off_btn = ttk.Button(frame, text="AUS (LOW)", command=lambda p=pin: self.set_pin(p, 0))
            state_lbl = ttk.Label(frame, text="Status: ...", width=20)

            on_btn.grid(row=0, column=0, padx=5)
            off_btn.grid(row=0, column=1, padx=5)
            state_lbl.grid(row=0, column=2, padx=5)

            self.labels[pin] = state_lbl

    def set_pin(self, pin, value):
        self.pi.write(pin, value)
        self.update_pin_state(pin)

    def update_pin_state(self, pin):
        value = self.pi.read(pin)
        text = "HIGH (1)" if value else "LOW (0)"
        self.labels[pin].config(text=f"Status: {text}")

    def update_pin_states(self):
        for pin in self.pins:
            self.update_pin_state(pin)
        self.after(500, self.update_pin_states)

    def on_close(self):
        for pin in self.pins:
            self.pi.write(pin, 0)  # Alles auf LOW beim Beenden
        self.pi.stop()
        self.destroy()

if __name__ == "__main__":
    pins = [17, 22, 24, 27]
    app = GPIORelayGUI(pins)
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()
