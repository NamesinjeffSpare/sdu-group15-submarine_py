# serial_link.py
#
# Bit-banged serial link between Raspberry Pi and Arduino/Seeeduino.
# RX only is enough for now; TX is optional.

import time
import pigpio

# ─────────────────────────────────────────────
# CHANGE THESE IF YOUR WIRING / BAUD IS DIFFERENT
# ─────────────────────────────────────────────
RX_GPIO = 20   # Pi pin connected to Arduino TX (D7)
TX_GPIO = 21   # Pi pin connected to Arduino RX (D6) - only used if you want to send
BAUD    = 9600 # Must match SoftwareSerial baud on Arduino
# ─────────────────────────────────────────────

_pi = None
_rx_buffer = ""
_tx_ready = False


def init_serial():
    """Call once at startup (or lazily)."""
    global _pi, _tx_ready

    if _pi is not None:
        return

    _pi = pigpio.pi()
    if not _pi.connected:
        raise RuntimeError("pigpiod not running. Run: sudo systemctl start pigpiod")

    # RX: bit-banged serial receive
    _pi.bb_serial_read_open(RX_GPIO, BAUD, 8)

    # TX: normal output pin (we will use wave_add_serial)
    _pi.set_mode(TX_GPIO, pigpio.OUTPUT)
    _tx_ready = True

    print(f"[serial_link] init: RX=GPIO{RX_GPIO}, TX=GPIO{TX_GPIO}, BAUD={BAUD}")


def close_serial():
    """Optional: close on shutdown."""
    global _pi
    if _pi is None:
        return
    try:
        _pi.bb_serial_read_close(RX_GPIO)
    except pigpio.error:
        pass
    _pi.stop()
    _pi = None
    print("[serial_link] closed")


def _parse_status_line(line: str):
    """
    Expect lines like:
    STATUS,is_deployed=1,percent_9v=80,percent_12v=60,emergency=0

    Returns a dict or None.
    """
    line = line.strip()
    if not line:
        return None
    if not line.startswith("STATUS"):
        return None

    parts = line.split(",")
    data = {"raw": line}

    for p in parts[1:]:
        if "=" in p:
            k, v = p.split("=", 1)
            k = k.strip()
            v = v.strip()
            # try int, fall back to string
            try:
                v_parsed = int(v)
            except ValueError:
                try:
                    v_parsed = float(v)
                except ValueError:
                    v_parsed = v
            data[k] = v_parsed

    return data


def read_seeeduino_status():
    """
    Non-blocking poll.
    Call this often (e.g. once per main loop).
    Returns:
      - dict with parsed STATUS fields (if a new STATUS line arrived)
      - or None if nothing new / not a STATUS line.
    """
    global _rx_buffer

    if _pi is None:
        init_serial()

    # read any new bytes
    count, data = _pi.bb_serial_read(RX_GPIO)
    if count <= 0:
        return None

    try:
        text = data.decode("ascii", errors="ignore")
    except Exception:
        return None

    _rx_buffer += text
    result = None

    # process complete lines
    while "\n" in _rx_buffer:
        line, _rx_buffer = _rx_buffer.split("\n", 1)
        line = line.rstrip("\r")
        if not line:
            continue

        # Debug: print everything we see
        # print("[serial_link] RX:", line)

        parsed = _parse_status_line(line)
        if parsed is not None:
            result = parsed

    return result


def _send_line(s: str):
    """Low-level: send one line (string) via TX using pigpio wave."""
    global _pi, _tx_ready
    if _pi is None:
        init_serial()
    if not _tx_ready:
        return

    _pi.wave_clear()
    _pi.wave_add_serial(TX_GPIO, BAUD, s.encode("ascii"))
    wid = _pi.wave_create()
    if wid >= 0:
        _pi.wave_send_once(wid)
        while _pi.wave_tx_busy():
            time.sleep(0.001)
        _pi.wave_delete(wid)


def send_goto_to_seeeduino(x: float, y: float, speed: float):
    """
    High-level command sender.
    Expected format on Arduino side (you can change it):
        GOTO,x=<x>,y=<y>,v=<speed>
    """
    line = f"GOTO,x={x},y={y},v={speed}\n"
    print("[serial_link] TX:", line.strip())
    _send_line(line)
