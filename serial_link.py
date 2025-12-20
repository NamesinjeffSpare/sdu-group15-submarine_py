import pigpio
import time

RX_GPIO = 20  # GPIO pin for RX (from Seeeduino TX)
TX_GPIO = 21  # GPIO pin for TX (to Seeeduino RX)
BAUD = 9600

_pi = None
_rx_buffer = bytearray()
_last_rx_time = 0.0


def init_serial():
    global _pi, _rx_buffer, _last_rx_time
    if _pi is not None:
        return

    _pi = pigpio.pi()
    if not _pi.connected:
        raise RuntimeError("pigpio daemon not running / not connected")

    # Set up TX as output, RX as input
    _pi.set_mode(TX_GPIO, pigpio.OUTPUT)
    _pi.set_mode(RX_GPIO, pigpio.INPUT)

    # Use pigpio serial read callback for RX
    def _rx_callback(gpio, level, tick):
        nonlocal _rx_buffer, _last_rx_time
        if level != pigpio.FALLING_EDGE:
            return
        try:
            b = _pi.serial_read_byte(RX_GPIO)  # may not be used depending on wiring
            _rx_buffer.append(b)
            _last_rx_time = time.time()
        except Exception:
            pass

    # We don't actually attach the callback here – reading is done using
    # the built-in serial read on a bit-banged UART. See read_seeeduino_status.
    _rx_buffer = bytearray()
    _last_rx_time = time.time()


def close_serial():
    global _pi
    if _pi is not None:
        _pi.stop()
        _pi = None


def _parse_status_line(line: str):
    """
    Parse a STATUS line from the Seeeduino into a dict.

    Format is:
      STATUS,key=value,key2=value2,...

    Values are kept as strings unless they look like ints/floats.
    """
    line = line.strip()
    if not line.startswith("STATUS,"):
        return None

    parts = line.split(",")[1:]
    result = {}
    for part in parts:
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        v = v.strip()
        # Try to parse numbers
        try:
            if "." in v:
                v_cast = float(v)
            else:
                v_cast = int(v)
            result[k] = v_cast
        except ValueError:
            result[k] = v
    return result


def read_seeeduino_status(timeout_s: float = 0.01):
    """
    Read a STATUS line from the Seeeduino if available.

    This assumes that the Seeeduino periodically sends newline-terminated
    ASCII lines. We look for lines starting with 'STATUS,' and parse them.
    """
    global _pi, _rx_buffer, _last_rx_time

    if _pi is None:
        init_serial()

    # Read available bytes from RX GPIO bit-banged serial
    try:
        count, data = _pi.bb_serial_read(RX_GPIO)
        if count > 0:
            _rx_buffer.extend(data)
            _last_rx_time = time.time()
    except pigpio.error:
        # If bb_serial_read isn't initialised, just ignore
        pass

    # Look for newline in buffer
    if b"\n" not in _rx_buffer:
        return None

    line_bytes, _, rest = _rx_buffer.partition(b"\n")
    _rx_buffer = bytearray(rest)

    try:
        line = line_bytes.decode("ascii", errors="ignore")
    except Exception:
        return None

    status = _parse_status_line(line)
    if status is not None:
        print("[SERIAL] RX STATUS:", status)
    return status


def _send_line(line: str):
    """
    Send a line of ASCII text to the Seeeduino using bit-banged serial.
    """
    global _pi
    if _pi is None:
        init_serial()

    if not line.endswith("\n"):
        line = line + "\n"

    data = line.encode("ascii")
    print("[SERIAL] TX RAW:", repr(line.strip()))

    # Simple blocking write using bit-banged serial
    _pi.bb_serial_write(TX_GPIO, data)


def send_goto_to_seeeduino(x_m: float, y_m: float, speed_ms: float):
    """
    Send a high-level GOTO command to the Seeeduino.

    Format:
      GOTO,x=...,y=...,v=...
    """
    line = f"GOTO,x={x_m:.2f},y={y_m:.2f},v={speed_ms:.2f}"
    _send_line(line)


# ---------------------------------------------------------------------------
# Small OO wrapper used by main.py (NanoLink / SerialLinkConfig)
# ---------------------------------------------------------------------------

class SerialLinkConfig:
    """Lightweight configuration for NanoLink.

    Currently the low-level implementation uses module-level constants
    RX_GPIO / TX_GPIO / BAUD, but we keep this object so existing code
    can pass a config without breaking.
    """

    def __init__(self, port="/dev/serial0", baud=BAUD,
                 rx_gpio=RX_GPIO, tx_gpio=TX_GPIO):
        self.port = port
        self.baud = baud
        self.rx_gpio = rx_gpio
        self.tx_gpio = tx_gpio


class NanoLink:
    """Small wrapper around the existing module-level helpers.

    It provides the interface used in main.py:
      - read_status()
      - send_goto(x, y, speed)
      - send_state(...)
    """

    def __init__(self, config):
        self.config = config
        # The current implementation uses pigpio bit-banged serial on the
        # module-level RX/TX pins. We initialise it here.
        init_serial()

    # --- API used from main.py ------------------------------------------------

    def read_status(self):
        return read_seeeduino_status()

    def send_goto(self, x, y, speed):
        send_goto_to_seeeduino(x, y, speed)

    def send_state(
        self,
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
        auto_flag = 1 if autonomous else 0
        parts = [
            "PI",
            f"ab={above_seabed_m:.2f}",
            f"auto={auto_flag}",
        ]

        if lat is not None:
            parts.append(f"lat={lat:.6f}")
        if lon is not None:
            parts.append(f"lon={lon:.6f}")
        if alt is not None:
            parts.append(f"alt={alt:.2f}")

        parts.extend(
            [
                f"temp={temp_c:.2f}",
                f"hum={hum_pct:.2f}",
                f"leak={int(bool(leakage))}",
            ]
        )

        if heading_deg is not None:
            parts.append(f"hdg={heading_deg:.2f}")

        line = ",".join(parts) + "\n"
        print("[serial_link] TX:", line.strip())
        _send_line(line)
