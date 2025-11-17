# main.py
import time
import os
import subprocess
import requests
from Neo6mGPS import open_gps, get_gps_fix

INFO_URL = "https://emils-pp.onrender.com/info"
UPDATE_URL = "https://emils-pp.onrender.com/update/"
UPLOAD_IMAGE_URL = "https://emils-pp.onrender.com/upload_image/"

BACKEND_REFRESH = 5      # seconds – how often we poll /info
GPS_INTERVAL = 1.0       # seconds – how often we try to send GPS updates
PHOTO_DIR = "/home/pi/photos"  # folder on SD card for photos

os.makedirs(PHOTO_DIR, exist_ok=True)


def get_time_seconds(timer_str):
    """Convert MM:SS -> seconds."""
    try:
        m, s = timer_str.split(":")
        return int(m) * 60 + int(s)
    except Exception:
        print("Invalid time format:", timer_str)
        return 0


def get_backend_state():
    try:
        r = requests.get(INFO_URL, timeout=3)
        return r.json()
    except Exception as e:
        print("Error fetching backend state:", e)
        return None


# --------------- FLASHLIGHT STUBS -----------------

def flashlight_on():
    # TODO: implement GPIO or whatever you use for the light
    print("[FLASHLIGHT] ON")


def flashlight_off():
    # TODO: implement GPIO off logic
    print("[FLASHLIGHT] OFF")


# --------------- CAMERA & STORAGE -----------------

def take_photo_to_file(filepath):
    cmd = ["libcamera-still", "-n", "-o", filepath]
    print("[CAMERA] Running:", " ".join(cmd))
    subprocess.run(cmd, check=True)
    print("[CAMERA] Saved:", filepath)


def capture_and_store_photo():
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = f"img_{timestamp}.jpg"
    filepath = os.path.join(PHOTO_DIR, filename)

    flashlight_on()
    try:
        take_photo_to_file(filepath)
    except subprocess.CalledProcessError as e:
        print("[CAMERA] Error taking photo:", e)
        filepath = None
    finally:
        flashlight_off()

    return filepath


def upload_image(filepath):
    if not os.path.exists(filepath):
        print("[UPLOAD] File does not exist:", filepath)
        return False

    try:
        with open(filepath, "rb") as f:
            files = {"file": (os.path.basename(filepath), f, "image/jpeg")}
            r = requests.post(UPLOAD_IMAGE_URL, files=files, timeout=15)
        print("[UPLOAD] Status:", r.status_code, r.text)
        return 200 <= r.status_code < 300
    except Exception as e:
        print("[UPLOAD] Error uploading", filepath, ":", e)
        return False


def upload_all_images():
    print("[UPLOAD] Uploading all images from", PHOTO_DIR)

    files = sorted(os.listdir(PHOTO_DIR))
    for name in files:
        if not name.lower().endswith((".jpg", ".jpeg", ".png")):
            continue

        filepath = os.path.join(PHOTO_DIR, name)
        success = upload_image(filepath)
        if success:
            try:
                os.remove(filepath)
                print("[UPLOAD] Deleted local file:", filepath)
            except OSError as e:
                print("[UPLOAD] Failed to delete", filepath, ":", e)


# --------------- MAIN LOOP -----------------

def main():
    # GPS init wrapped in try/except so failure doesn't kill program
    try:
        gps = open_gps()
    except Exception as e:
        print("[GPS] Error opening GPS:", e)
        gps = None

    backend = get_backend_state() or {
        "explore": False,
        "autonomous": True,
        "meters": 0,
        "time": "0:05",
        "sVoltage": 0,
        "sDry": 0,
        "sMemory": 0,
    }

    photo_interval = get_time_seconds(backend["time"])

    last_gps_send = 0.0
    last_backend = 0.0
    last_photo_time = 0.0

    prev_explore = backend["explore"]

    print("Running main loop...")
    print("  GPS interval     =", GPS_INTERVAL, "seconds (constant)")
    print("  Photo interval   =", photo_interval, "seconds (from backend)")

    while True:
        now = time.time()

        # --- 1) Update backend state periodically ---
        if now - last_backend >= BACKEND_REFRESH:
            new_state = get_backend_state()
            if new_state:
                backend = new_state
                photo_interval = get_time_seconds(backend["time"])
                print("[BACKEND] Updated photo interval:", photo_interval)

                # Example trigger: explore True -> False
                if prev_explore and not backend["explore"]:
                    print("[TRIGGER] Explore disabled -> uploading all images")
                    upload_all_images()

                prev_explore = backend["explore"]

            last_backend = now

        # --- 2) GPS updates (safe even if GPS is dead or submerged) ---
        if now - last_gps_send >= GPS_INTERVAL:
            fix = None
            if gps is not None:
                try:
                    fix = get_gps_fix(gps)
                except Exception as e:
                    print("[GPS] Error getting fix:", e)
                    fix = None

            if fix:
                print("[GPS]", fix)

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
                    print("[UPDATE] Status:", r.status_code)
                except Exception as e:
                    print("[UPDATE] POST error:", e)
            else:
                print("[GPS] No fix or GPS unavailable – skipping update")

            last_gps_send = now

        # --- 3) Photo capture based on backend time interval ---
        if photo_interval > 0 and (now - last_photo_time) >= photo_interval:
            print("[CAMERA] Time to take photo")
            filepath = capture_and_store_photo()
            if filepath:
                print("[CAMERA] Stored photo at:", filepath)
            last_photo_time = now

        time.sleep(0.1)


if __name__ == "__main__":
    main()
