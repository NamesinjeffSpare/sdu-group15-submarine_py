import board
import busio
import adafruit_vl6180x
import requests
import time
import RPi.GPIO as GPIO
from hx711 import HX711

GPIO.setmode(GPIO.BCM)
# range sensor based on this https://wiki.dfrobot.com/DFRobot_VL6180X_TOF_Distance_Ranging_Sensor_Breakout_Board_SKU_SEN0427
i2c = busio.I2C(board.SCL, board.SDA)
sensor = adafruit_vl6180x.VL6180X(i2c)

url = 'https://emil.onrender.com/info'

# pins were set based on this https://pinout.xyz/pinout/pin3_gpio2/
GPIO.setup(17, GPIO.OUT)

#weight sensor based on this: https://www.diyengineers.com/2022/05/19/load-cell-with-hx711-how-to-use-with-examples/ & this: https://github.com/mpibpc-mroose/hx711/tree/master/hx711
hx = HX711(dout_pin=5, pd_sck_pin=6, gain=128, channel='A')
hx.reset()
offset = sum(hx.get_raw_data(42)) / 42

def get_distance():
    distance = sensor.range
    return distance

def get_weight():
    raw_data = hx.get_raw_data(3)
    avg_raw = (sum(raw_data) / len(raw_data)) - offset
    # Data from the trials
    weight = 0.9320512871030306 * avg_raw + 2156.0249059522744
    return weight

def start_motor():
    GPIO.output(17, GPIO.HIGH)

def stop_motor():
    GPIO.output(17, GPIO.LOW)

def get_timefeed(timer):
    timef = timer.split(":")
    hour = int(timef[0])
    minute = int(timef[1])
    return minute * 60 + hour * 3600

if __name__ == "__main__":
    try:
        start_time = time.time()
        current_timefeed = None

        while True:
            #Grabbing data from the sensors
            distance = get_distance()
            weight = get_weight()
            # Grabbing the data from the server
            response = requests.get(url)

            if response.status_code == 200:
                data = response.json()
                tofeed = data["feed"]
                vol = data["volume"]
                timer = data["time"]

                new_timefeed = get_timefeed(timer)
                if new_timefeed != current_timefeed:
                    current_timefeed = new_timefeed
                    start_time = time.time()

                elapsed_time = time.time() - start_time
                if elapsed_time >= current_timefeed:
                    if tofeed and vol > weight and distance >= 150:
                        start_motor()

                        while vol > weight and distance >= 150:
                            distance = get_distance()
                            weight = get_weight()

                        stop_motor()
                        start_time = time.time()
                    else:
                        stop_motor()
                else:
                    pass
            else:
                pass
    finally:
        GPIO.cleanup()
