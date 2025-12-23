# flashlight.py
try:
    import RPi.GPIO as GPIO
except ImportError:
    GPIO = None


class Flashlight:
    
    def __init__(self, pin=5, active_high=True, initial_off=True):
        if GPIO is None:
            raise RuntimeError("RPi.GPIO not available")

        self.pin = int(pin)
        self.active_high = bool(active_high)

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.pin, GPIO.OUT)

        if initial_off:
            self.off()

    def on(self):
        GPIO.output(self.pin, GPIO.HIGH if self.active_high else GPIO.LOW)

    def off(self):
        GPIO.output(self.pin, GPIO.LOW if self.active_high else GPIO.HIGH)

    def cleanup(self):
        try:
            self.off()
        finally:
            GPIO.cleanup(self.pin)
