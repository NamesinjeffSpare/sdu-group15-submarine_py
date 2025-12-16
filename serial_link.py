# serial_link.py
import time
import pigpio


class SerialLink:
    """
    Bit-banged UART using pigpio.
    - RX uses bb_serial_read_open()
    - TX uses wave_add_serial() (reliable TX)
    """

    def __init__(self, rx_gpio: int, tx_gpio: int, baud: int = 115200):
        self.rx_gpio = rx_gpio
        self.tx_gpio = tx_gpio
        self.baud = baud

        self.pi = pigpio.pi()
        if not self.pi.connected:
            raise RuntimeError("pigpio daemon not running. Start with: sudo systemctl start pigpiod")

        self.pi.set_mode(self.tx_gpio, pigpio.OUTPUT)
        self.pi.write(self.tx_gpio, 1)  # idle HIGH

        self.pi.set_mode(self.rx_gpio, pigpio.INPUT)
        self.pi.bb_serial_read_open(self.rx_gpio, self.baud)

        self._rx_buf = b""

    def close(self):
        try:
            self.pi.bb_serial_read_close(self.rx_gpio)
        except Exception:
            pass
        self.pi.stop()

    def send_line(self, s: str):
        data = (s.rstrip("\n") + "\n").encode("utf-8")
        self.pi.wave_clear()
        self.pi.wave_add_serial(self.tx_gpio, self.baud, data)
        wid = self.pi.wave_create()
        if wid < 0:
            raise RuntimeError("Failed to create pigpio wave for serial TX")
        self.pi.wave_send_once(wid)
        while self.pi.wave_tx_busy():
            time.sleep(0.001)
        self.pi.wave_delete(wid)

    def read_available_lines(self):
        """
        Returns list[str] of complete lines received since last call.
        """
        count, data = self.pi.bb_serial_read(self.rx_gpio)
        if count > 0:
            self._rx_buf += data

        lines = []
        while b"\n" in self._rx_buf:
            line, self._rx_buf = self._rx_buf.split(b"\n", 1)
            line = line.strip(b"\r")
            try:
                lines.append(line.decode("utf-8", errors="ignore"))
            except Exception:
                pass
        return lines
