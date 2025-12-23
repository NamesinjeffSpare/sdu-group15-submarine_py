# test_leakage_sensor.py
import time
from leakage_sensor import LeakageSensor, LeakageConfig

LEAKAGE_GPIO_PIN = 12   

cfg = LeakageConfig(
    pin=LEAKAGE_GPIO_PIN,
    sample_period_s=0.1,   # 100 ms
    debounce_count=10,     # ~1 second confirmation
    active_low=True        # matches your AVR logic
)

sensor = LeakageSensor(cfg)

print("Leakage sensor test started")
print("Waiting for leakage...")
print("Press CTRL+C to exit")

try:
    while True:
        triggered = sensor.update()

        if triggered:
            print("🚨 LEAKAGE DETECTED (LATCHED) 🚨")

        # Optional live state print
        if sensor.is_latched():
            print("State: LATCHED")
        else:
            print("State: OK")

        time.sleep(0.1)

except KeyboardInterrupt:
    print("\nExiting test")

finally:
    sensor.cleanup()
    print("GPIO cleaned up")
