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

BACKEND_REFRESH = 5      # seconds – how often we poll the backend
GPS_INTERVAL = 5         # seconds – how often we send GPS + state
PHOTO_DIR = "/home/pi/photos"
CAMERA_AREA_M2 = 4.0     # footprint area in m^2 for each photo (example)

_SERIAL_CONFIG = SerialLinkConfig(
    port="/dev/serial0",
    baud=9600,
    rx_gpio=20,
    tx_gpio=21,
)
_link = NanoLink(_SERIAL_CONFIG)


def read_seeeduino_status():
    return _link.read_status()


def send_goto_to_seeeduino(x_m, y_m, speed_ms):
    return _link.send_goto(x_m, y_m, speed_ms)


def send_state_to_seeeduino(
    above_seabed_m,
    autonomous,
    lat,
    lon,
    alt,
    temp_c,
    hum_pct,
    leakage,
    heading_deg=None,
):
    """
    Send state packet to Seeeduino. serial_link.NanoLink is expected to
    turn this into the 'PI,...' line for the microcontroller.

    heading_deg allows the Raspberry Pi to calibrate the submarine's
    forward direction using GPS and pass that on to the microcontroller.
    If heading_deg is None the field is omitted.
    """
    return _link.send_state(
        above_seabed_m=above_seabed_m,
        autonomous=autonomous,
        lat=lat,
        lon=lon,
        alt=alt,
        temp_c=temp_c,
        hum_pct=hum_pct,
        leakage=leakage,
        heading_deg=heading_deg,
    )


def get_backend_state():
    try:
        r = requests.get(INFO_URL, timeout=6)
        if r.status_code == 200:
            return r.json()
        else:
            print("[BACKEND] /info/ status", r.status_code)
    except Exception as e:
        print("[BACKEND] /info/ error:", e)
    return None


def get_free_sd_mb(path="/"):
    total, used, free = shutil.disk_usage(path)
    return free // (1024 * 1024)


def get_time_seconds(t_str):
    parts = t_str.split(":")
    if len(parts) == 1:
        return int(parts[0])
    if len(parts) == 2:
        minutes = int(parts[0])
        seconds = int(parts[1])
        return minutes * 60 + seconds
    return 0


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


def bearing_deg(lat1, lon1, lat2, lon2):
    """Compute bearing in degrees from (lat1, lon1) to (lat2, lon2).

    Returns a value in [0, 360) or None if the movement is too small.
    """
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return None

    # Rough check to avoid division by zero / noise
    if abs(lat2 - lat1) < 1e-6 and abs(lon2 - lon1) < 1e-6:
        return None

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dlon = math.radians(lon2 - lon1)

    y = math.sin(dlon) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlon)

    bearing = math.degrees(math.atan2(y, x))
    bearing = (bearing + 360.0) % 360.0
    return bearing


def point_in_polygon(x, y, polygon):
    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / (yj - yi + 1e-9) + xi
        ):
            inside = not inside
        j = i
    return inside


def generate_coverage_waypoints(polygon, camera_area_m2, photo_interval_s):
    if not polygon:
        return []

    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    lane_spacing = math.sqrt(camera_area_m2) * 0.8
    waypoints = []

    y = min_y
    direction = 1
    while y <= max_y:
        if direction > 0:
            x_range = (min_x, max_x)
        else:
            x_range = (max_x, min_x)

        steps = int(abs(x_range[1] - x_range[0]) / lane_spacing) + 1
        for i in range(steps + 1):
            x = x_range[0] + (x_range[1] - x_range[0]) * (i / max(1, steps))
            if point_in_polygon(x, y, polygon):
                waypoints.append((x, y))

        direction *= -1
        y += lane_spacing

    return waypoints


def internet_available():
    try:
        requests.get("https://www.google.com", timeout=3)
        return True
    except Exception:
        return False


def capture_and_store_photo():
    os.makedirs(PHOTO_DIR, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(PHOTO_DIR, f"photo_{timestamp}.jpg")

    try:
        cmd = [
            "libcamera-still",
            "-o",
            filepath,
            "--width",
            "1920",
            "--height",
            "1080",
            "--autofocus-on-capture",
        ]
        subprocess.run(cmd, check=True)
        return filepath
    except Exception as e:
        print("[CAMERA] Capture error:", e)
        return None


def upload_image(filepath):
    if not internet_available():
        print("[UPLOAD] No internet, skipping upload for now")
        return False

    try:
        with open(filepath, "rb") as f:
            files = {"file": f}
            r = requests.post(UPLOAD_IMAGE_URL, files=files, timeout=10)
        if r.status_code == 200:
            print("[UPLOAD] Success:", filepath)
            return True
        print("[UPLOAD] Failed with status:", r.status_code)
    except Exception as e:
        print("[UPLOAD] Error:", e)
    return False


def upload_all_images():
    if not os.path.isdir(PHOTO_DIR):
        return

    for name in sorted(os.listdir(PHOTO_DIR)):
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


def navigation_step(
    status,
    backend_state,
    traverse_speed,
    coverage_waypoints,
    coverage_index,
    command_in_flight,
    failed_waypoints,
):
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

    if (
        not command_in_flight
        and backend_state.get("explore", False)
        and traverse_speed is not None
    ):
        if coverage_index < len(coverage_waypoints):
            x, y = coverage_waypoints[coverage_index]
            print(
                "[COVERAGE] Sending waypoint",
                coverage_index,
                "->",
                (x, y),
                "speed",
                traverse_speed,
            )
            send_goto_to_seeeduino(x, y, traverse_speed)
            command_in_flight = True
            coverage_index += 1
        else:
            print("[COVERAGE] All waypoints visited; stopping exploration.")
            backend_state["explore"] = False

    return coverage_index, command_in_flight, failed_waypoints


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

    # --- Local sensors on the Raspberry Pi ---
    temp_sensor = None
    leakage_sensor = None
    flashlight = None

    try:
        temp_sensor = TemperatureSensor()
        print("[TEMP] TemperatureSensor initialised")
    except Exception as e:
        print("[TEMP] Error initialising TemperatureSensor:", e)

    try:
        leak_cfg = LeakageConfig(
            pin=12,             # BCM 12 (see leakage_test.py)
            sample_period_s=0.1,
            debounce_count=10,
            active_low=True
        )
        leakage_sensor = LeakageSensor(leak_cfg)
        print("[LEAK] LeakageSensor initialised on GPIO", leak_cfg.pin)
    except Exception as e:
        print("[LEAK] Error initialising LeakageSensor:", e)

    try:
        flashlight = Flashlight()
        print("[FLASH] Flashlight initialised")
    except Exception as e:
        print("[FLASH] Error initialising Flashlight:", e)

    # Keep last known position so backend still updates even with no GPS fix
    last_lat = backend.get("lat", 54.9130)
    last_lon = backend.get("lon", 9.7785)
    last_alt = backend.get("alt", 0.0)
    # Previous GPS fix used to compute heading
    prev_lat = None
    prev_lon = None
    gps_heading_deg = None

    # Status LED on the Raspberry Pi
    rgb = RGB()
    led_state = None

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
        has_warning = False
        leak_latched = False

        # --- leakage sensor update ---
        if leakage_sensor is not None:
            try:
                if leakage_sensor.update():
                    print("[LEAK] Leak detected – state latched")
                leak_latched = leakage_sensor.is_latched()
            except Exception as e:
                print("[LEAK] Error reading leakage sensor:", e)

        if leak_latched:
            has_warning = True

        status = read_seeeduino_status()
        if status is not None:
            warning0 = int(
                round((failed_waypoints / total_waypoints_planned) * 100)
            ) if total_waypoints_planned > 0 else 0
            if not isinstance(status, dict):
                status = {}
            status.setdefault("warning_types", [])
            if len(status["warning_types"]) == 0:
                status["warning_types"].append(warning0)
            else:
                status["warning_types"][0] = warning0

            # Derive a simple warning flag for the RGB LED
            if bool(status.get("emergency_active")) or status.get("emergency_reason_mask", 0):
                has_warning = True
            ultra_err = status.get("ultrasonic_error_latched")
            if isinstance(ultra_err, (list, tuple)) and any(ultra_err):
                has_warning = True

            try:
                r_old = requests.post(OLD_URL, json=status, timeout=6)
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

        # --- poll backend state ------------------------------------------------
        if now - last_backend >= BACKEND_REFRESH:
            new_state = get_backend_state()
            if new_state:
                backend = new_state
                backend["polygon"] = backend.get("polygon") or []

                photo_interval = get_time_seconds(backend.get("time", "0:05"))
                traverse_speed = recommended_speed(CAMERA_AREA_M2, photo_interval)
                photos_needed = compute_photos_needed(
                    backend["polygon"], CAMERA_AREA_M2
                )
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

        # --- ALWAYS send update to backend + state to Seeeduino ---
        if now - last_send >= GPS_INTERVAL:
            fix = None
            if gps is not None:
                try:
                    fix = get_gps_fix(gps)
                except Exception as e:
                    print("[GPS] Error getting fix:", e)

            if fix:
                # Use consecutive fixes to estimate heading for calibration.
                prev_lat, prev_lon = last_lat, last_lon
                last_lat, last_lon, last_alt = fix["lat"], fix["lon"], fix["alt"]
                gps_h = bearing_deg(prev_lat, prev_lon, last_lat, last_lon)
                if gps_h is not None:
                    gps_heading_deg = gps_h
                    print("[GPS] Fix:", fix, "heading_deg=", gps_heading_deg)
                else:
                    print("[GPS] Fix:", fix)
            else:
                print("[GPS] No fix – sending last known position")

            # --- local environmental sensors (temp / humidity) ---
            temp_c = 0.0
            hum_pct = 0.0
            if temp_sensor is not None:
                try:
                    reading = temp_sensor.update()
                    if reading:
                        temp_c = float(reading.get("temp_c", temp_c))
                        hum_pct = float(reading.get("humidity", hum_pct))
                    elif getattr(temp_sensor, "last_ok", None) is not None:
                        temp_c = float(temp_sensor.last_ok.get("temp_c", temp_c))
                        hum_pct = float(temp_sensor.last_ok.get("humidity", hum_pct))
                except Exception as e:
                    print("[TEMP] Read error:", e)

            # Send telemetry to backend (Pi does NOT overwrite mission config)
            payload = {
                "explore": backend.get("explore", False),
                "autonomous": backend.get("autonomous", True),
                "meters": backend.get("meters", 0),
                "sMemory": get_free_sd_mb(PHOTO_DIR),
                "sVoltage": backend.get("sVoltage", 0),
                "sDry": backend.get("sDry", 0),
                "time": backend.get("time", "0:05"),
                "lat": last_lat,
                "lon": last_lon,
                "alt": last_alt,
                "polygon": backend.get("polygon", []),
                "temperature": temp_c,
                "humidity": hum_pct,
                "leakage": int(bool(leak_latched)),
            }

            try:
                r = requests.post(UPDATE_URL, json=payload, timeout=6)
                print("[UPDATE] Status:", r.status_code)
            except Exception as e:
                print("[UPDATE] POST error:", e)

            # --- ALSO send state to Seeeduino over serial ---

            above_seabed_m = backend.get("meters", 0)
            autonomous = backend.get("autonomous", True)

            try:
                send_state_to_seeeduino(
                    above_seabed_m=above_seabed_m,
                    autonomous=autonomous,
                    lat=last_lat,
                    lon=last_lon,
                    alt=last_alt,
                    temp_c=temp_c,
                    hum_pct=hum_pct,
                    leakage=bool(leak_latched),
                    heading_deg=gps_heading_deg,
                )
            except Exception as e:
                print("[SERIAL] Error sending state to Seeeduino:", e)

            last_send = now

        # --- LED status (Pi RGB) ---
        try:
            if gps is not None and gps_heading_deg is None:
                desired_led = "calibrating"
            elif has_warning:
                desired_led = "warning"
            elif backend.get("explore", False):
                # Sub is deployed / running mission
                desired_led = "deployed"
            else:
                desired_led = "awaiting"

            if desired_led != led_state:
                rgb.set_state(desired_led)
                led_state = desired_led
        except Exception as e:
            print("[LED] Error updating RGB LED:", e)

        # --- photo capture (flashlight on before photo, off after) ---
        if photo_interval > 0 and (now - last_photo_time) >= photo_interval:
            print("[CAMERA] Time to take photo")
            # Turn on flashlight for the shot
            if flashlight is not None:
                try:
                    flashlight.on()
                    print("[FLASH] On for photo")
                except Exception as e:
                    print("[FLASH] Error turning on flashlight:", e)

            filepath = capture_and_store_photo()

            # Turn off flashlight after the shot
            if flashlight is not None:
                try:
                    flashlight.off()
                    print("[FLASH] Off after photo")
                except Exception as e:
                    print("[FLASH] Error turning off flashlight:", e)

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
