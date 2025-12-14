import time
import board
from temperature_sensor import TemperatureSensor

ts = TemperatureSensor(pin=board.D4, sensor_type="DHT11", interval_s=3.0)

while True:
    r = ts.update()
    if r:
        print(r)
    time.sleep(0.1)
