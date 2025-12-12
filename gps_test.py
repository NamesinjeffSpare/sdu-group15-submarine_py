import serial
import time

ser = serial.Serial("/dev/serial0", 9600, timeout=1)

print("Listening for GPS data...")

last_data = time.time()

while True:
    line = ser.readline().decode("ascii", errors="ignore").strip()
    if line:
        print(line)
        last_data = time.time()
    else:
        if time.time() - last_data > 2:
            print("NO DATA (check wiring / power)")
            last_data = time.time()
