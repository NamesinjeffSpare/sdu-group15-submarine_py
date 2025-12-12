# Neo6mGPS.py

import serial
import pynmea2

GPS_PORT = "/dev/serial0"
GPS_BAUD = 9600

def open_gps():
    return serial.Serial(GPS_PORT, GPS_BAUD, timeout=0.5)

def get_gps_fix(ser):
    for _ in range(20):
        try:
            line = ser.readline().decode("ascii", errors="replace").strip()
            if "GGA" not in line:
                continue

            msg = pynmea2.parse(line)

            if not msg.latitude or not msg.longitude:
                continue
            if not msg.gps_qual or int(msg.gps_qual) == 0:
                continue

            return {
                "lat": float(msg.latitude),
                "lon": float(msg.longitude),
                "alt": float(msg.altitude or 0.0),
            }
        except Exception:
            pass
    return None
