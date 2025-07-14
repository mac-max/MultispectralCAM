import pigpio
import time

class IRFilterController:
    def __init__(self, pin_pulse=2, pin_dir=3, pulse_duration=0.05):
        self.pi = pigpio.pi()  # Verbindung zum Daemon
        if not self.pi.connected:
            raise RuntimeError("pigpio daemon is not running")

        self.pin_pulse = pin_pulse
        self.pin_dir = pin_dir
        self.pulse_duration = pulse_duration

        self.pi.set_mode(self.pin_pulse, pigpio.OUTPUT)
        self.pi.set_mode(self.pin_dir, pigpio.OUTPUT)

    def _send_pulse(self):
        self.pi.write(self.pin_pulse, 1)
        time.sleep(self.pulse_duration)
        self.pi.write(self.pin_pulse, 0)

    def switch_in(self):
        self.pi.write(self.pin_dir, 1)
        self._send_pulse()

    def switch_out(self):
        self.pi.write(self.pin_dir, 0)
        self._send_pulse()

    def cleanup(self):
        self.pi.stop()
