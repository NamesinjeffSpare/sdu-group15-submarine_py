# leakage_sensor.py
import time

try:
    import RPi.GPIO as GPIO
except ImportError:
    GPIO = None


class LeakageConfig:
    def __init__(
        self,
        pin,
        sample_period_s=0.1,
        debounce_count=10,
        active_low=True
    ):
        self.pin = pin
        self.sample_period_s = sample_period_s
        self.debounce_count = debounce_count
        self.active_low = active_low


class LeakageSensor:
    def __init__(self, config: LeakageConfig):
        if GPIO is None:
            raise RuntimeError("RPi.GPIO not available")

        self.cfg = config
        self._low_count = 0
        self._high_count = 0
        self._latched = False
        self._last_sample = 0.0

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(
            self.cfg.pin,
            GPIO.IN,
            pull_up_down=GPIO.PUD_UP if self.cfg.active_low else GPIO.PUD_DOWN
        )

    def update(self):
        """
        Call periodically.
        Returns True ONCE when leakage is confirmed.
        """
        now = time.time()
        if now - self._last_sample < self.cfg.sample_period_s:
            return False
        self._last_sample = now

        level = GPIO.input(self.cfg.pin)

        is_active = (level == GPIO.LOW) if self.cfg.active_low else (level == GPIO.HIGH)

        if is_active:
            self._low_count += 1
            self._high_count = 0
        else:
            self._high_count += 1
            self._low_count = 0

        if self._low_count >= self.cfg.debounce_count and not self._latched:
            self._latched = True
            return True

        return False

    def is_latched(self):
        return self._latched

    def cleanup(self):
        GPIO.cleanup(self.cfg.pin)
