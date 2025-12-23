# Neo6mGPS.py
# Clean NEO-6M GPS reader using serial + pynmea2

import serial
import pynmea2

GPS_PORT = "/dev/serial0"
GPS_BAUD = 9600

def open_gps():

    return serial.Serial(GPS_PORT, GPS_BAUD, timeout=0.5)

def get_gps_fix(ser):
    for _ in range(30):
        try:
            line_bytes = ser.readline()
            if not line_bytes:
                continue

            line = line_bytes.decode("ascii", errors="replace").strip()
            if "GGA" not in line:
                continue

            msg = pynmea2.parse(line)

            # Require a real fix quality
            if not getattr(msg, "gps_qual", None) or int(msg.gps_qual) == 0:
                continue

            if msg.latitude is None or msg.longitude is None:
                continue

            lat = float(msg.latitude)
            lon = float(msg.longitude)
            alt = float(msg.altitude) if msg.altitude else 0.0

            return {"lat": lat, "lon": lon, "alt": alt}

        except Exception:
            pass

    return None
