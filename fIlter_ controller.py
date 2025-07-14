import RPi.GPIO as GPIO
import time

class IRFilterController:
    def __init__(self, pin_pulse=2, pin_dir=3, pulse_duration=0.05):
        self.pin_pulse = pin_pulse
        self.pin_dir = pin_dir
        self.pulse_duration = pulse_duration

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.pin_pulse, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(self.pin_dir, GPIO.OUT, initial=GPIO.LOW)

    def _send_pulse(self):
        GPIO.output(self.pin_pulse, GPIO.HIGH)
        time.sleep(self.pulse_duration)
        GPIO.output(self.pin_pulse, GPIO.LOW)

    def switch_in(self):
        """IR-Filter einschwenken"""
        GPIO.output(self.pin_dir, GPIO.HIGH)
        self._send_pulse()

    def switch_out(self):
        """IR-Filter ausschwenken"""
        GPIO.output(self.pin_dir, GPIO.LOW)
        self._send_pulse()

    def cleanup(self):
        """GPIO-Pins freigeben"""
        GPIO.cleanup((self.pin_pulse, self.pin_dir))
