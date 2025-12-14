from gpiozero import DHT11
from time import sleep

sensor = DHT11(4)

while True:
    sensor.measure()
    print(sensor.temperature, sensor.humidity)
    sleep(3)
