import time
import RPi.GPIO as GPIO

FLASHLIGHT_PIN = 5      # GPIO5 
BLINKS = 10             
ON_TIME = 0.5           
OFF_TIME = 0.5          

GPIO.setmode(GPIO.BCM)
GPIO.setup(FLASHLIGHT_PIN, GPIO.OUT)

print("Starting flashlight blink test...")

try:
    for i in range(BLINKS):
        GPIO.output(FLASHLIGHT_PIN, GPIO.HIGH) 
        print(f"Blink {i+1}: ON")
        time.sleep(ON_TIME)

        GPIO.output(FLASHLIGHT_PIN, GPIO.LOW)   
        print(f"Blink {i+1}: OFF")
        time.sleep(OFF_TIME)

finally:
    GPIO.output(FLASHLIGHT_PIN, GPIO.LOW)
    GPIO.cleanup()
    print("Blink test finished, GPIO cleaned up.")
