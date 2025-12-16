# main.py
import time
import os
import subprocess
import requests
import math
import shutil

from flashlight import Flashlight
from leakage_sensor import LeakageConfig, LeakageSensor
from RGB import RGB
from tempreture_sensor import TemperatureSensor
from Neo6mGPS import open_gps, get_gps_fix
from serial_link import NanoLink, SerialLinkConfig

INFO_URL = "https://emils-pp.onrender.com/info/"
UPDATE_URL = "https://emils-pp.onrender.com/update/"
UPLOAD_IMAGE_URL = "https://emils-pp.onrender.com/upload_image/"
OLD_URL = "https://emils-pp.onrender.com/old/"

BACKEND_REFRESH = 5      # seconds – how often we poll /info
GPS_INTERVAL = 1.0       # seconds – how often we try to send updates
PHOTO_DIR = os.path.join(os.path.expanduser("~"), "photos")
CAMERA_AREA_M2 = 1.0

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
        r = requests.get(INFO_URL, timeout=6)
        return r.json()
    except Exception as e:
        print("Error fetching backend state:", e)
        return None


def get_free_sd_mb(path=PHOTO_DIR):
    """
    Free space (MB) on the filesystem that stores PHOTO_DIR.
    This reports real SD card free space to backend.
    """
    try:
        st = os.statvfs(path)
        free_bytes = st.f_bavail * st.f_frsize
        return int(free_bytes / (1024 * 1024))
    except Exception as e:
        print("[SD] Error reading free space:", e)
        return 0


def internet_available():
    """
    Fast connectivity check to your backend.
    """
    try:
        requests.get(INFO_URL, timeout=3)
        return True
    except Exception:
        return False


def polygon_area_m2(polygon):
    if not polygon or len(polygon) < 3:
        return 0.0
    area = 0.0
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    return abs(area) * 0.5


def compute_photos_needed(polygon, camera_area_m2):
    if camera_area_m2 <= 0:
        return 0
    area = polygon_area_m2(polygon)
    if area <= 0:
        return 0
    return math.ceil(area / camera_area_m2)


def recommended_speed(camera_area_m2, photo_interval_s):
    if camera_area_m2 <= 0 or photo_interval_s <= 0:
        return None
    footprint_length = math.sqrt(camera_area_m2)
    return footprint_length / photo_interval_s


def point_in_polygon(x, y, polygon):
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        intersect = ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / (yj - yi + 1e-9) + xi
        )
        if intersect:
            inside = not inside
        j = i
    return inside


def generate_coverage_waypoints(polygon, camera_area_m2, photo_interval_s):
    if not polygon:
        return []
    if len(polygon) == 1:
        return [tuple(polygon[0])]

    step = math.sqrt(camera_area_m2) if camera_area_m2 > 0 else 0.0

    if len(polygon) == 2 or step <= 0:
        x1, y1 = polygon[0]
        x2, y2 = polygon[1]
        dx = x2 - x1
        dy = y2 - y1
        dist = math.hypot(dx, dy)
        if dist == 0:
            return [tuple(polygon[0])]
        along = step if step > 0 else dist
        n = max(1, int(math.ceil(dist / along)))
        waypoints = []
        for i in range(n + 1):
            t = i / n
            waypoints.append((x1 + t * dx, y1 + t * dy))
        return waypoints

    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    min_x = min(xs)
    max_x = max(xs)
    min_y = min(ys)
    max_y = max(ys)

    if step <= 0:
        step = max(max_x - min_x, max_y - min_y)

    waypoints = []
    y = min_y
    direction = 1
    while y <= max_y + 1e-9:
        if direction > 0:
            x_start, x_end = min_x, max_x
        else:
            x_start, x_end = max_x, min_x

        length = abs(x_end - x_start)
        segments = max(1, int(math.ceil(length / step)))
        for i in range(segments + 1):
            t = i / segments
            x = x_start + t * (x_end - x_start)
            if point_in_polygon(x, y, polygon):
                waypoints.append((x, y))

        direction *= -1
        y += step

    if not waypoints:
        cx = sum(xs) / len(xs)
        cy = sum(ys) / len(ys)
        waypoints.append((cx, cy))

    return waypoints


# --------------- SEEEDUINO STUBS -----------------

# --- Serial link (Arduino Nano / Seeeduino) ---
_link = NanoLink(SerialLinkConfig(port="/dev/ttyUSB0", baud=115200))

def read_seeeduino_status():
    # returns dict or None
    return _link.read_status()

def send_goto_to_seeeduino(x, y, speed):
    # include GPS context if you want (optional)
    return _link.send_goto(x, y, speed)


def navigation_step(status, backend, traverse_speed, coverage_waypoints, coverage_index, command_in_flight, failed_waypoints):
    nav_state = None
    if status is not None and isinstance(status, dict):
        nav_state = status.get("nav_state")

    if command_in_flight:
        if nav_state == "busy":
            return coverage_index, command_in_flight, failed_waypoints
        if nav_state == "failed":
            failed_waypoints += 1
            command_in_flight = False
        elif nav_state == "arrived":
            command_in_flight = False

    if (not command_in_flight) and backend.get("explore") and traverse_speed is not None:
        if coverage_index < len(coverage_waypoints):
            x, y = coverage_waypoints[coverage_index]
            send_goto_to_seeeduino(x, y, traverse_speed)
            command_in_flight = True
            coverage_index += 1

    return coverage_index, command_in_flight, failed_waypoints


# --------------- FLASHLIGHT STUBS -----------------

def flashlight_on():
    print("[FLASHLIGHT] ON")


def flashlight_off():
    print("[FLASHLIGHT] OFF")


# --------------- CAMERA & STORAGE -----------------

def take_photo_to_file(filepath):
    cam = shutil.which("rpicam-still") or shutil.which("libcamera-still")
    if not cam:
        raise FileNotFoundError("No camera tool found: rpicam-still/libcamera-still")

    cmd = [cam, "-n", "-o", filepath]
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
    except Exception as e:
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
            r = requests.post(UPLOAD_IMAGE_URL, files=files, timeout=30)
        print("[UPLOAD] Status:", r.status_code, r.text)
        return 200 <= r.status_code < 300
    except Exception as e:
        print("[UPLOAD] Error uploading", filepath, ":", e)
        return False


def upload_all_images():
    # Only attempt if online
    if not internet_available():
        print("[UPLOAD] No internet – queued images kept on SD")
        return

    print("[UPLOAD] Internet detected – uploading queued images from", PHOTO_DIR)

    files = sorted(os.listdir(PHOTO_DIR))
    for name in files:
        if not name.lower().endswith((".jpg", ".jpeg", ".png")):
            continue

        filepath = os.path.join(PHOTO_DIR, name)
        print("[UPLOAD] Trying:", filepath)

        success = upload_image(filepath)
        if success:
            try:
                os.remove(filepath)
                print("[UPLOAD] Uploaded + deleted:", filepath)
            except OSError as e:
                print("[UPLOAD] Failed to delete", filepath, ":", e)
        else:
            print("[UPLOAD] Failed – will retry later:", filepath)
            # stop on first failure (likely connection dropped)
            break


# --------------- MAIN LOOP -----------------

def main():
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
        "lat": 54.9130,
        "lon": 9.7785,
        "alt": 0.0,
        "polygon": [],
    }

    if "polygon" not in backend or backend["polygon"] is None:
        backend["polygon"] = []

    # Keep last known position so backend still updates even with no GPS fix
    last_lat = backend.get("lat", 54.9130)
    last_lon = backend.get("lon", 9.7785)
    last_alt = backend.get("alt", 0.0)

    photo_interval = get_time_seconds(backend.get("time", "0:05"))
    traverse_speed = recommended_speed(CAMERA_AREA_M2, photo_interval)
    photos_needed = compute_photos_needed(backend["polygon"], CAMERA_AREA_M2)
    coverage_waypoints = generate_coverage_waypoints(
        backend["polygon"], CAMERA_AREA_M2, photo_interval
    )

    coverage_index = 0
    command_in_flight = False
    total_waypoints_planned = len(coverage_waypoints)
    failed_waypoints = 0

    last_send = 0.0
    last_backend = 0.0
    last_photo_time = 0.0
    last_upload_attempt = 0.0
    prev_explore = backend.get("explore", False)

    print("Running main loop...")
    print("  Update interval  =", GPS_INTERVAL, "seconds")
    print("  Backend poll     =", BACKEND_REFRESH, "seconds")
    print("  Photo interval   =", photo_interval, "seconds")
    print("  Photo dir        =", PHOTO_DIR)
    print("  Coverage wps     =", len(coverage_waypoints))

    while True:
        now = time.time()

        status = read_seeeduino_status()
        if status is not None:
            warning0 = int(round((failed_waypoints / total_waypoints_planned) * 100)) if total_waypoints_planned > 0 else 0
            if not isinstance(status, dict):
                status = {}
            status.setdefault("warning_types", [])
            if len(status["warning_types"]) == 0:
                status["warning_types"].append(warning0)
            else:
                status["warning_types"][0] = warning0

            try:
                r_old = requests.post(OLD_URL, json=status, timeout=6)
                print("[OLD] Status:", r_old.status_code)
            except Exception as e:
                print("[OLD] POST error:", e)

        coverage_index, command_in_flight, failed_waypoints = navigation_step(
            status, backend, traverse_speed,
            coverage_waypoints, coverage_index,
            command_in_flight, failed_waypoints
        )

        # --- poll backend state ---
        if now - last_backend >= BACKEND_REFRESH:
            new_state = get_backend_state()
            if new_state:
                backend = new_state
                backend["polygon"] = backend.get("polygon") or []

                photo_interval = get_time_seconds(backend.get("time", "0:05"))
                traverse_speed = recommended_speed(CAMERA_AREA_M2, photo_interval)
                photos_needed = compute_photos_needed(backend["polygon"], CAMERA_AREA_M2)
                coverage_waypoints = generate_coverage_waypoints(
                    backend["polygon"], CAMERA_AREA_M2, photo_interval
                )
                coverage_index = 0
                command_in_flight = False
                total_waypoints_planned = len(coverage_waypoints)
                failed_waypoints = 0

                print("[BACKEND] Updated photo interval:", photo_interval)
                print("[COVERAGE] photos_needed:", photos_needed)
                print("[COVERAGE] traverse_speed:", traverse_speed)
                print("[COVERAGE] waypoints:", len(coverage_waypoints))

                # Existing trigger kept
                if prev_explore and not backend.get("explore", False):
                    print("[TRIGGER] Explore disabled -> uploading all images")
                    upload_all_images()

                prev_explore = backend.get("explore", False)

            last_backend = now

        # --- ALWAYS send update to backend ---
        if now - last_send >= GPS_INTERVAL:
            fix = None
            if gps is not None:
                try:
                    fix = get_gps_fix(gps)
                except Exception as e:
                    print("[GPS] Error getting fix:", e)

            if fix:
                last_lat, last_lon, last_alt = fix["lat"], fix["lon"], fix["alt"]
                print("[GPS] Fix:", fix)
            else:
                print("[GPS] No fix – sending last known position")

            payload = {
                "explore": backend.get("explore", False),
                "autonomous": backend.get("autonomous", True),
                "meters": backend.get("meters", 0),

                # REAL free SD space (MB)
                "sMemory": get_free_sd_mb(),

                "sVoltage": backend.get("sVoltage", 0),
                "sDry": backend.get("sDry", 0),
                "time": backend.get("time", "0:05"),
                "lat": last_lat,
                "lon": last_lon,
                "alt": last_alt,
                "polygon": backend.get("polygon", []),
            }

            try:
                r = requests.post(UPDATE_URL, json=payload, timeout=6)
                print("[UPDATE] Status:", r.status_code)
            except Exception as e:
                print("[UPDATE] POST error:", e)

            last_send = now

        # --- photo capture ---
        if photo_interval > 0 and (now - last_photo_time) >= photo_interval:
            print("[CAMERA] Time to take photo")
            filepath = capture_and_store_photo()
            if filepath:
                print("[CAMERA] Stored photo at:", filepath)
            last_photo_time = now

        # --- attempt upload periodically when internet is available ---
        # (does nothing underwater, uploads everything when back online)
        if now - last_upload_attempt >= 10.0:
            upload_all_images()
            last_upload_attempt = now



if __name__ == "__main__":
    main()
