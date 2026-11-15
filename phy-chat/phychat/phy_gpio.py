"""GPIO physical layer for the BeagleBone Black (Linux sysfs GPIO).

TX per tick: drive the data lanes, wait setup time, raise CLK, hold, drop CLK.
RX: wait for a rising edge on CLK, optionally wait sample_delay (slow media),
then read the data lanes. Whatever sits between TX pin and RX pin (wire,
LED + phototransistor, buzzer + mic...) only has to reproduce 0/1.
"""
import glob
import os
import select
import threading
import time

# Header pin -> GPIO number (bank*32 + line), BeagleBone Black
HEADER = {
    "P8_7": 66, "P8_8": 67, "P8_9": 69, "P8_10": 68, "P8_11": 45, "P8_12": 44,
    "P8_13": 23, "P8_14": 26, "P8_15": 47, "P8_16": 46, "P8_17": 27, "P8_18": 65,
    "P8_19": 22, "P8_26": 61, "P9_12": 60, "P9_15": 48, "P9_23": 49, "P9_27": 115,
    "P9_30": 112,
}
_BANK_ADDR = {"44e07000": 0, "4804c000": 1, "481ac000": 2, "481ae000": 3}
SYSFS = "/sys/class/gpio"
PINMUX = "/sys/devices/platform/ocp/ocp:%s_pinmux/state"


def _bank_bases():
    """Newer kernels may number gpiochips dynamically; map each bank to its sysfs base."""
    bases = {}
    for chip in glob.glob(SYSFS + "/gpiochip*"):
        try:
            with open(chip + "/base") as f:
                base = int(f.read())
            ident = os.path.realpath(chip + "/device")
            with open(chip + "/label") as f:
                ident += f.read()
        except OSError:
            continue
        for addr, bank in _BANK_ADDR.items():
            if addr in ident:
                bases[bank] = base
    return bases


def sysfs_number(pin):
    n = HEADER[pin] if isinstance(pin, str) else int(pin)
    bank, line = divmod(n, 32)
    return _bank_bases().get(bank, bank * 32) + line


def _write(path, value, retries=50):
    # right after export, udev may still be fixing permissions
    for _ in range(retries):
        try:
            with open(path, "w") as f:
                f.write(value)
            return
        except PermissionError:
            time.sleep(0.02)
    with open(path, "w") as f:
        f.write(value)


def set_mode(pin, mode):
    # in pinmux mode "default" the sysfs value can change while the header pin does not
    header, num = pin.split("_")
    path = PINMUX % ("%s_%02d" % (header, int(num)))
    if os.path.exists(path):
        _write(path, mode)


class Pin:
    def __init__(self, pin, direction):
        self.label = pin
        if isinstance(pin, str):
            set_mode(pin, "gpio" if direction == "out" else "gpio_pd")
        self.n = sysfs_number(pin)
        self.path = "%s/gpio%d" % (SYSFS, self.n)
        if not os.path.exists(self.path):
            _write(SYSFS + "/export", str(self.n))
            for _ in range(50):
                if os.path.exists(self.path):
                    break
                time.sleep(0.02)
        _write(self.path + "/direction", "low" if direction == "out" else "in")
        mode = os.O_RDWR if direction == "out" else os.O_RDONLY
        self.fd = os.open(self.path + "/value", mode)

    def write(self, v):
        os.write(self.fd, b"1" if v else b"0")

    def read(self):
        os.lseek(self.fd, 0, os.SEEK_SET)
        return 1 if os.read(self.fd, 2)[:1] == b"1" else 0

    def set_edge(self, edge):
        _write(self.path + "/edge", edge)


class GpioPhy:
    kind = "gpio"

    def __init__(self, tx, rx, hz, sample_delay=0.0, poll_s=0.0005):
        """tx / rx: {"clk": "P8_7", "data": ["P8_8", "P8_9"]}"""
        if len(tx["data"]) != len(rx["data"]):
            raise ValueError("TX and RX need the same number of data lanes")
        self.lanes = len(tx["data"])
        self.hz = hz
        self.sample_delay = sample_delay
        self.poll_s = poll_s
        self.tx_clk = Pin(tx["clk"], "out")
        self.tx_data = [Pin(p, "out") for p in tx["data"]]
        self.rx_clk = Pin(rx["clk"], "in")
        self.rx_data = [Pin(p, "in") for p in rx["data"]]
        self.on_tick = None

    def start(self):
        threading.Thread(target=self._rx_loop, daemon=True).start()

    def send_ticks(self, ticks):
        half = 0.5 / self.hz
        t_next = time.monotonic()
        for tick in ticks:
            for pin, bit in zip(self.tx_data, tick):
                pin.write(bit)
            t_next += half
            self._sleep_until(t_next)
            self.tx_clk.write(1)
            t_next += half
            self._sleep_until(t_next)
            self.tx_clk.write(0)
        for pin in self.tx_data:
            pin.write(0)

    @staticmethod
    def _sleep_until(t):
        delay = t - time.monotonic()
        if delay > 0:
            time.sleep(delay)

    def _sample(self):
        if self.sample_delay:
            time.sleep(self.sample_delay)
        self.on_tick([p.read() for p in self.rx_data], time.monotonic())

    def _rx_loop(self):
        try:
            self.rx_clk.set_edge("rising")
            poller = select.poll()
            poller.register(self.rx_clk.fd, select.POLLPRI | select.POLLERR)
            self.rx_clk.read()
        except OSError:
            return self._rx_poll_loop()
        while True:
            if poller.poll(500):
                self.rx_clk.read()
                self._sample()

    def _rx_poll_loop(self):
        prev = self.rx_clk.read()
        while True:
            v = self.rx_clk.read()
            if v and not prev:
                self._sample()
            prev = v
            time.sleep(self.poll_s)
