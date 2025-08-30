import pigpio
import time

class IRFilterController:
    def __init__(self, pin_in=2, pin_out=3, pulse_duration=0.05):
        self.pi = pigpio.pi()
        if not self.pi.connected:
            raise RuntimeError("pigpio daemon is not running")

        self.pin_in = pin_in      # GPIO for "switch in" pulse
        self.pin_out = pin_out    # GPIO for "switch out" pulse
        self.pulse_duration = pulse_duration

        self.pi.set_mode(self.pin_in, pigpio.OUTPUT)
        self.pi.set_mode(self.pin_out, pigpio.OUTPUT)
        self.pi.write(self.pin_in, 0)
        self.pi.write(self.pin_out, 0)

    def switch_in(self):
        """IR-Filter einschwenken"""
        self.pi.write(self.pin_out, 0)
        self.pi.write(self.pin_in, 1)
        time.sleep(self.pulse_duration)
        self.pi.write(self.pin_in, 0)

    def switch_out(self):
        """IR-Filter ausschwenken"""
        self.pi.write(self.pin_in, 0)
        self.pi.write(self.pin_out, 1)
        time.sleep(self.pulse_duration)
        self.pi.write(self.pin_out, 0)

    def cleanup(self):
        self.pi.stop()