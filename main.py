# main.py
import time
import requests
from Neo6mGPS import open_gps, get_gps_fix

INFO_URL = "https://emils-pp.onrender.com/info"
UPDATE_URL = "https://emils-pp.onrender.com/update/"

BACKEND_REFRESH = 5  # seconds

def get_time_seconds(timer_str):
    """Convert MM:SS → seconds."""
    try:
        m, s = timer_str.split(":")
        return int(m) * 60 + int(s)
    except:
        print("Invalid time format:", timer_str)
        return 0

def get_backend_state():
    try:
        r = requests.get(INFO_URL, timeout=3)
        return r.json()
    except:
        return None

def main():
    gps = open_gps()

    backend = get_backend_state() or {
        "explore": False,
        "autonomous": True,
        "meters": 0,
        "time": "0:05",
        "sVoltage": 0,
        "sDry": 0,
        "sMemory": 0
    }

    interval = get_time_seconds(backend["time"])
    last_send = time.time()
    last_backend = time.time()

    print("Running main loop... interval =", interval, "seconds")

    while True:
        now = time.time()

        # Update backend state
        if now - last_backend >= BACKEND_REFRESH:
            new_state = get_backend_state()
            if new_state:
                backend = new_state
                interval = get_time_seconds(backend["time"])
                print("Updated interval:", interval)
            last_backend = now

        # Time to send GPS update?
        if now - last_send >= interval:
            fix = get_gps_fix(gps)

            if fix:
                print("GPS:", fix)
            else:
                print("No GPS fix")
                fix = {"lat": 0.0, "lon": 0.0, "alt": 0.0}

            payload = {
                "explore": backend["explore"],
                "autonomous": backend["autonomous"],
                "meters": backend["meters"],
                "sMemory": backend["sMemory"],
                "sVoltage": backend["sVoltage"],
                "sDry": backend["sDry"],
                "time": backend["time"],
                "lat": fix["lat"],
                "lon": fix["lon"],
                "alt": fix["alt"]
            }

            try:
                r = requests.post(UPDATE_URL, json=payload, timeout=3)
                print("Update:", r.status_code)
            except Exception as e:
                print("POST error:", e)

            last_send = now

        time.sleep(0.1)

if __name__ == "__main__":
    main()
