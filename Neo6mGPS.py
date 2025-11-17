import serial
import pynmea2

GPS_PORT = "/dev/ttyAMA0"   # or "/dev/serial0"
GPS_BAUD = 9600

def open_gps():
    """Open and return GPS serial device."""
    return serial.Serial(GPS_PORT, GPS_BAUD, timeout=0.5)

def get_gps_fix(ser):
    """
    Read GPS until we get a valid GGA fix.
    Returns dict: { lat, lon, alt } or None.
    """
    for _ in range(20):
        try:
            line_bytes = ser.readline()
            if not line_bytes:
                continue

            line = line_bytes.decode("ascii", errors="replace").strip()

            if "GGA" not in line:
                continue

            msg = pynmea2.parse(line)

            if msg.latitude is None or msg.longitude is None:
                continue

            lat = float(msg.latitude)
            lon = float(msg.longitude)
            alt = float(msg.altitude) if msg.altitude else 0.0

            return {"lat": lat, "lon": lon, "alt": alt}

        except Exception:
            pass

    return None
