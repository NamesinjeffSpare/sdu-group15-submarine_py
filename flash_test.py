# test_flashlight.py
import time
from flashlight import Flashlight

PIN = 5          # GPIO5 (BCM)
BLINKS = 10      # number of blinks
ON_TIME = 0.5    # seconds ON
OFF_TIME = 0.5   # seconds OFF

light = Flashlight(pin=PIN, active_high=True)

print("Starting flashlight blink test...")

try:
    for i in range(BLINKS):
        light.on()
        print(f"Blink {i+1}: ON")
        time.sleep(ON_TIME)

        light.off()
        print(f"Blink {i+1}: OFF")
        time.sleep(OFF_TIME)

finally:
    light.off()
    light.cleanup()
    print("Blink test finished, GPIO cleaned up.")
