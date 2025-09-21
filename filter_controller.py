import pigpio
import time

class IRFilterController:
    def __init__(self, pin_in=22, pin_out=27, pin_pos=17, pin_neg=24, pulse_duration=0.5):
        self.pi = pigpio.pi()
        if not self.pi.connected:
            raise RuntimeError("pigpio daemon is not running")

        self.pin_in = pin_in
        self.pin_out = pin_out
        self.pin_pos = pin_pos
        self.pin_neg = pin_neg
        self.pulse_duration = pulse_duration

        self.pi.set_mode(self.pin_in, pigpio.OUTPUT)
        self.pi.set_mode(self.pin_out, pigpio.OUTPUT)
        self.pi.write(self.pin_in, 0)
        self.pi.write(self.pin_out, 0)

        self.pi.set_mode(self.pin_pos, pigpio.OUTPUT)
        self.pi.set_mode(self.pin_neg, pigpio.OUTPUT)
        self.pi.write(self.pin_pos, 0)
        self.pi.write(self.pin_neg, 0)


    def switch_in(self):
        """IR-Filter einschwenken"""
        self.pi.write(self.pin_out, 1)
        self.pi.write(self.pin_in, 1)
        self.pi.write(self.pin_pos, 1)
        self.pi.write(self.pin_neg, 1)
        time.sleep(self.pulse_duration)
        self.pi.write(self.pin_out, 0)
        self.pi.write(self.pin_in, 0)
        self.pi.write(self.pin_pos, 0)
        self.pi.write(self.pin_neg, 0)


    def switch_out(self):
        """IR-Filter ausschwenken"""
        self.pi.write(self.pin_out, 0)
        self.pi.write(self.pin_in, 0)
        self.pi.write(self.pin_pos, 1)
        self.pi.write(self.pin_neg, 1)
        time.sleep(self.pulse_duration)
        self.pi.write(self.pin_out, 0)
        self.pi.write(self.pin_in, 0)
        self.pi.write(self.pin_pos, 0)
        self.pi.write(self.pin_neg, 0)


    def cleanup(self):
        self.pi.stop()
