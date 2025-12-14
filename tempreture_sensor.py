# dht_sensor.py
import time
import board
import adafruit_dht


class DHTReader:
    """
    Non-blocking-ish DHT reader.
    Call .update() frequently; it will only read every read_interval_s.
    """

    def __init__(self, pin=board.D4, read_interval_s=3.0, sensor_type="DHT11"):
        self.read_interval_s = float(read_interval_s)
        self.last_read = 0.0

        if sensor_type.upper() == "DHT22":
            self.sensor = adafruit_dht.DHT22(pin)
        else:
            self.sensor = adafruit_dht.DHT11(pin)

        self.last_ok = None  

    def update(self):
        """
        Returns latest reading dict if a new read succeeded, else None.
        Never raises RuntimeError (DHT is flaky); only raises unexpected exceptions.
        """
        now = time.time()
        if now - self.last_read < self.read_interval_s:
            return None
        self.last_read = now

        try:
            temp_c = self.sensor.temperature
            hum = self.sensor.humidity

            # Sometimes the library returns None
            if temp_c is None or hum is None:
                return None

            temp_f = temp_c * (9.0 / 5.0) + 32.0

            self.last_ok = {
                "temp_c": float(temp_c),
                "temp_f": float(temp_f),
                "humidity": float(hum),
            }
            return self.last_ok

        except RuntimeError:
            # Normal for DHT sensors (checksum/timeouts)
            return None

    def close(self):
        try:
            self.sensor.exit()
        except Exception:
            pass
