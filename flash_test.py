import time
import RPi.GPIO as GPIO

FLASHLIGHT_PIN = 5      # GPIO5 (BCM)
BLINKS = 10             # number of blinks
ON_TIME = 0.5           # seconds ON
OFF_TIME = 0.5          # seconds OFF

GPIO.setmode(GPIO.BCM)
GPIO.setup(FLASHLIGHT_PIN, GPIO.OUT)

print("Starting flashlight blink test...")

try:
    for i in range(BLINKS):
        GPIO.output(FLASHLIGHT_PIN, GPIO.HIGH)  # flashlight ON
        print(f"Blink {i+1}: ON")
        time.sleep(ON_TIME)


finally:
    GPIO.output(FLASHLIGHT_PIN, GPIO.LOW)
    GPIO.cleanup()
    print("Blink test finished, GPIO cleaned up.")
