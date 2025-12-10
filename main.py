# main.py
import time
import os
import subprocess
import requests
import math
from Neo6mGPS import open_gps, get_gps_fix

INFO_URL = "https://emils-pp.onrender.com/info"
UPDATE_URL = "https://emils-pp.onrender.com/update/"
UPLOAD_IMAGE_URL = "https://emils-pp.onrender.com/upload_image/"
OLD_URL = "https://emils-pp.onrender.com/old/"

BACKEND_REFRESH = 5      # seconds – how often we poll /info
GPS_INTERVAL = 1.0       # seconds – how often we try to send GPS updates
PHOTO_DIR = "/home/pi/photos"  # folder on SD card for photos
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
        r = requests.get(INFO_URL, timeout=3)
        return r.json()
    except Exception as e:
        print("Error fetching backend state:", e)
        return None


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


def read_seeeduino_status():
    return None


def send_goto_to_seeeduino(x, y, speed):
    print("[SEND GOTO]", x, y, speed)


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
        "polygon": [],
    }

    if "polygon" not in backend or backend["polygon"] is None:
        backend["polygon"] = []

    photo_interval = get_time_seconds(backend["time"])
    traverse_speed = recommended_speed(CAMERA_AREA_M2, photo_interval)
    photos_needed = compute_photos_needed(backend["polygon"], CAMERA_AREA_M2)
    coverage_waypoints = generate_coverage_waypoints(
        backend["polygon"], CAMERA_AREA_M2, photo_interval
    )
    coverage_index = 0
    command_in_flight = False
    total_waypoints_planned = len(coverage_waypoints)
    failed_waypoints = 0

    last_gps_send = 0.0
    last_backend = 0.0
    last_photo_time = 0.0

    prev_explore = backend["explore"]

    print("Running main loop...")
    print("  GPS interval     =", GPS_INTERVAL, "seconds (constant)")
    print("  Photo interval   =", photo_interval, "seconds (from backend)")
    print("  Camera area m^2  =", CAMERA_AREA_M2)
    print("  Polygon points   =", len(backend["polygon"]))
    print("  Photos needed    =", photos_needed)
    print("  Traverse speed m/s (no overlap) =", traverse_speed)
    print("  Coverage wps     =", len(coverage_waypoints))

    while True:
        now = time.time()

        status = read_seeeduino_status()
        if status is not None:
            if total_waypoints_planned > 0:
                failure_ratio = failed_waypoints / total_waypoints_planned
                warning0 = int(round(failure_ratio * 100))
            else:
                warning0 = 0

            if not isinstance(status, dict):
                status = {}
            if "warning_types" not in status or not isinstance(status["warning_types"], list):
                status["warning_types"] = []
            if len(status["warning_types"]) == 0:
                status["warning_types"].append(warning0)
            else:
                status["warning_types"][0] = warning0

            try:
                r_old = requests.post(OLD_URL, json=status, timeout=3)
                print("[OLD] Status:", r_old.status_code)
            except Exception as e:
                print("[OLD] POST error:", e)

        coverage_index, command_in_flight, failed_waypoints = navigation_step(
            status,
            backend,
            traverse_speed,
            coverage_waypoints,
            coverage_index,
            command_in_flight,
            failed_waypoints,
        )

        # --- 1) Update backend state periodically ---
        if now - last_backend >= BACKEND_REFRESH:
            new_state = get_backend_state()
            if new_state:
                backend = new_state
                if "polygon" not in backend or backend["polygon"] is None:
                    backend["polygon"] = []
                photo_interval = get_time_seconds(backend["time"])
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
                print("[COVERAGE] traverse_speed m/s (no overlap):", traverse_speed)
                print("[COVERAGE] waypoints:", len(coverage_waypoints))

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
                    "alt": fix["alt"],
                    "polygon": backend["polygon"],
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
