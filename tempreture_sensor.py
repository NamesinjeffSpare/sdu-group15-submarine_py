# temperature_sensor.py
import time
import board
import adafruit_dht


class TemperatureSensor:

    def __init__(self, pin=board.D4, sensor_type="DHT11", interval_s=3.0):
        self.interval_s = float(interval_s)
        self.last_read = 0.0
        self.last_ok = None

        st = sensor_type.upper().strip()
        if st == "DHT22":
            self.sensor = adafruit_dht.DHT22(pin)
        else:
            self.sensor = adafruit_dht.DHT11(pin)

    def update(self):

        now = time.time()
        if now - self.last_read < self.interval_s:
            return None
        self.last_read = now

        try:
            temp_c = self.sensor.temperature
            hum = self.sensor.humidity

            if temp_c is None or hum is None:
                return None

            temp_f = temp_c * 9.0 / 5.0 + 32.0
            self.last_ok = {
                "temp_c": float(temp_c),
                "temp_f": float(temp_f),
                "humidity": float(hum),
                "ts": now,
            }
            return self.last_ok

        except RuntimeError:

            return None

    def close(self):
        try:
            self.sensor.exit()
        except Exception:
            pass
