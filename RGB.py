# RGB.py
try:
    import RPi.GPIO as GPIO
except ImportError:
    GPIO = None


class RGB:
    """Simple RGB LED helper.

    By default it assumes a common-cathode LED wired to BCM pins
    17 (red), 27 (green), 22 (blue). If your wiring is different you
    can pass the pin numbers when constructing the class.

    Colours used in main.py:
      - blue      -> awaiting commands
      - green     -> deployed / running mission
      - red       -> warning / error
      - "calibrating" state reuses blue but is set explicitly
    """

    def __init__(self, pin_r=17, pin_g=27, pin_b=22, active_high=True):
        self.pin_r = pin_r
        self.pin_g = pin_g
        self.pin_b = pin_b
        self.active_high = active_high
        self._last_state = None

        if GPIO is not None:
            GPIO.setmode(GPIO.BCM)
            for pin in (self.pin_r, self.pin_g, self.pin_b):
                GPIO.setup(pin, GPIO.OUT)
            self.off()

    def _write_pin(self, pin, on):
        if GPIO is None:
            return
        if self.active_high:
            GPIO.output(pin, GPIO.HIGH if on else GPIO.LOW)
        else:
            GPIO.output(pin, GPIO.LOW if on else GPIO.HIGH)

    def _set_raw(self, r, g, b):
        """Internal: set raw channel booleans."""
        self._last_state = (r, g, b)
        if GPIO is None:
            # When running on a non-Pi development machine, just log.
            print(f"[RGB] R={int(r)} G={int(g)} B={int(b)}")
            return

        self._write_pin(self.pin_r, r)
        self._write_pin(self.pin_g, g)
        self._write_pin(self.pin_b, b)

    # --- basic colours -------------------------------------------------------

    def off(self):
        self._set_raw(False, False, False)

    def set_red(self):
        self._set_raw(True, False, False)

    def set_green(self):
        self._set_raw(False, True, False)

    def set_blue(self):
        self._set_raw(False, False, True)

    # --- high-level states used by main.py -----------------------------------

    def set_state(self, state):
        """Set LED state by logical name.

        state can be one of:
          - "awaiting"     -> blue
          - "deployed"     -> green
          - "warning"      -> red
          - "calibrating"  -> currently also blue (but set explicitly)
        """
        if state == "awaiting":
            self.set_blue()
        elif state == "deployed":
            self.set_green()
        elif state == "warning":
            self.set_red()
        elif state == "calibrating":
            # For now, reuse blue for calibration. If you wire a
            # different colour you can change it here.
            self.set_blue()
        else:
            # Unknown state – turn LED off to avoid confusion
            self.off()

    def cleanup(self):
        if GPIO is not None:
            self.off()
            GPIO.cleanup((self.pin_r, self.pin_g, self.pin_b))
