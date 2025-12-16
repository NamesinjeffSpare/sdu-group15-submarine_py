# tech_expo.py
import time
import os
import subprocess
import requests
import math
import shutil

INFO_URL = "https://emils-pp.onrender.com/info/"
UPDATE_URL = "https://emils-pp.onrender.com/update/"
UPLOAD_IMAGE_URL = "https://emils-pp.onrender.com/upload_image/"

BACKEND_REFRESH = 1.0
WAYPOINT_INTERVAL = 0.5
UPLOAD_ATTEMPT_INTERVAL = 10.0

PHOTO_DIR = os.path.join(os.path.expanduser("~"), "photos")
CAMERA_AREA_M2 = 1.0

# ✅ NEW: hard stop for test scripts
TEST_TIMEOUT_SECONDS = 5

os.makedirs(PHOTO_DIR, exist_ok=True)

# Map "name" from UI -> python file to run
TEST_SCRIPTS = {
    "flash_test": "flash_test.py",
    "flashlight": "flashlight.py",
    "gps_test": "gps_test.py",
    "leakage_test": "leakage_test.py",
    "RGB_test": "RGB_test.py",
    "temperature_test": "tempreture_test.py",
    "serial_test": "serial_commucation_test.py",
}


# ---------------- BACKEND HELPERS ----------------

def get_backend_state():
    try:
        r = requests.get(INFO_URL, timeout=6)
        return r.json()
    except Exception as e:
        print("[BACKEND] Error fetching state:", e)
        return None


def post_update(payload: dict):
    try:
        r = requests.post(UPDATE_URL, json=payload, timeout=6)
        return r.status_code
    except Exception as e:
        print("[BACKEND] Error posting update:", e)
        return None


def internet_available():
    try:
        requests.get(INFO_URL, timeout=3)
        return True
    except Exception:
        return False


def get_time_seconds(timer_str):
    try:
        m, s = timer_str.split(":")
        return int(m) * 60 + int(s)
    except Exception:
        print("[TIME] Invalid time format:", timer_str)
        return 0


def get_free_sd_mb(path=PHOTO_DIR):
    try:
        st = os.statvfs(path)
        free_bytes = st.f_bavail * st.f_frsize
        return int(free_bytes / (1024 * 1024))
    except Exception as e:
        print("[SD] Error reading free space:", e)
        return 0


# ---------------- COVERAGE ----------------

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


def generate_coverage_waypoints(polygon, camera_area_m2):
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


# ---------------- CAMERA + STORAGE ----------------

def flashlight_on():
    print("[FLASHLIGHT] ON")


def flashlight_off():
    print("[FLASHLIGHT] OFF")


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
            break


# ---------------- COMMAND EXECUTION ----------------

def run_test_script(script_name):
    here = os.path.dirname(os.path.abspath(__file__))
    script_path = os.path.join(here, script_name)

    if not os.path.exists(script_path):
        raise FileNotFoundError(script_path)

    print("[TECH_EXPO] Running test:", script_path)

    # ✅ CHANGED: timeout after 5 seconds (kills infinite while loops)
    subprocess.run(
        ["python3", script_path],
        check=True,
        timeout=TEST_TIMEOUT_SECONDS
    )


def handle_command(cmd_name: str):
    # Special commands (not python test scripts)
    if cmd_name == "take_photo":
        fp = capture_and_store_photo()
        if fp:
            # Try immediate upload if online (otherwise queued)
            if internet_available():
                ok = upload_image(fp)
                if ok:
                    try:
                        os.remove(fp)
                    except OSError:
                        pass
                    return True, "photo taken + uploaded"
                return True, "photo taken (upload failed, queued)"
            return True, "photo taken (queued, offline)"
        return False, "camera error (no file)"

    if cmd_name == "upload_images":
        upload_all_images()
        return True, "upload attempted"

    # Script-based commands
    if cmd_name in TEST_SCRIPTS:
        try:
            run_test_script(TEST_SCRIPTS[cmd_name])
            return True, "ok"
        except subprocess.TimeoutExpired:
            return False, f"timeout ({TEST_TIMEOUT_SECONDS}s)"
        except Exception as e:
            return False, str(e)

    return False, f"Unknown command: {cmd_name}"


# ---------------- MAIN LOOP ----------------

def main():
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
        "command": None,
        "command_status": None,
        "next_x": None,
        "next_y": None,
    }

    backend["polygon"] = backend.get("polygon") or []

    coverage_waypoints = generate_coverage_waypoints(backend["polygon"], CAMERA_AREA_M2)
    wp_index = 0

    last_backend = 0.0
    last_waypoint_post = 0.0
    last_upload_attempt = 0.0
    last_command_id = None

    prev_explore = backend.get("explore", False)

    print("[TECH_EXPO] Running expo loop (waypoints + camera + commands)")

    while True:
        now = time.time()

        # --- poll backend state ---
        if now - last_backend >= BACKEND_REFRESH:
            new_state = get_backend_state()
            if new_state:
                backend = new_state
                backend["polygon"] = backend.get("polygon") or []

                # recompute waypoints if polygon changed
                coverage_waypoints = generate_coverage_waypoints(backend["polygon"], CAMERA_AREA_M2)
                if coverage_waypoints:
                    wp_index %= len(coverage_waypoints)
                else:
                    wp_index = 0

                # Upload everything when explore turns off (same idea as main)
                if prev_explore and not backend.get("explore", False):
                    print("[TRIGGER] Explore disabled -> uploading all images")
                    upload_all_images()
                prev_explore = backend.get("explore", False)

            last_backend = now

        # --- handle website command ---
        cmd = backend.get("command")
        if isinstance(cmd, dict):
            cmd_id = cmd.get("id")
            cmd_name = cmd.get("name")

            if cmd_id and cmd_id != last_command_id:
                last_command_id = cmd_id

                post_update({
                    "command_status": {"id": cmd_id, "state": "running", "msg": cmd_name}
                })

                try:
                    ok, msg = handle_command(cmd_name)
                    post_update({
                        "command_status": {
                            "id": cmd_id,
                            "state": "done" if ok else "error",
                            "msg": msg
                        },
                        "command": None
                    })
                except Exception as e:
                    post_update({
                        "command_status": {"id": cmd_id, "state": "error", "msg": str(e)},
                        "command": None
                    })

        # --- compute + post next waypoint every 0.5s ---
        if now - last_waypoint_post >= WAYPOINT_INTERVAL:
            next_x = None
            next_y = None

            if backend.get("explore") and coverage_waypoints:
                wp_index %= len(coverage_waypoints)
                next_x, next_y = coverage_waypoints[wp_index]
                wp_index += 1

            post_update({
                "next_x": next_x,
                "next_y": next_y,
                "sMemory": get_free_sd_mb(),
            })
            last_waypoint_post = now

        # --- periodic upload attempt ---
        if now - last_upload_attempt >= UPLOAD_ATTEMPT_INTERVAL:
            upload_all_images()
            last_upload_attempt = now

        time.sleep(0.05)


if __name__ == "__main__":
    main()
