import time
from serial_link import SerialLink

#uses physical pins 38/40:
# Pin 38 = GPIO20, Pin 40 = GPIO21
RX_GPIO = 20
TX_GPIO = 21

ser = SerialLink(rx_gpio=RX_GPIO, tx_gpio=TX_GPIO, baud=115200)

try:
    t0 = time.time()
    while True:
        ser.send_line("PING")
        for line in ser.read_available_lines():
            print("RX:", line)
        time.sleep(1.0)
        if time.time() - t0 > 30:
            break
finally:
    ser.close()
