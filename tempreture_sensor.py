import time

import adafruit_dht
import board

PIN = board.D4  # GPIO4

print("[DHT] Starting DHT11 on GPIO4 (board.D4)...")

sensor = adafruit_dht.DHT11(PIN)

while True:
    try:
        temperature_c = sensor.temperature
        humidity = sensor.humidity

        if temperature_c is None or humidity is None:
            print("[DHT] Read returned None (retrying...)")
        else:
            temperature_f = temperature_c * 9.0 / 5.0 + 32.0
            print(
                "Temp={0:0.1f}°C Temp={1:0.1f}°F Humidity={2:0.1f}%".format(
                    temperature_c, temperature_f, humidity
                )
            )

    except RuntimeError as e:
        # Expected sometimes for DHT sensors
        print("[DHT] RuntimeError:", e)

    except Exception as e:
        print("[DHT] Fatal error:", e)
        try:
            sensor.exit()
        except Exception:
            pass
        raise

    time.sleep(3.0)
