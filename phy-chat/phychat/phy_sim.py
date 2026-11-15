"""Simulated physical medium: one UDP datagram per clock tick.

Each datagram carries every channel's samples for that tick (see linecode).
Pacing is real (hz), so link timeouts behave as they will on hardware.

Interference is applied on the receive side, like someone disturbing a
sensor, one mode per channel, held until switched off or for N ticks:
  block     hand between emitter and sensor: the sensor sees all 0
  saturate  IR pointer on the sensor: all 1
  noise     every sample random
noise_p additionally flips any sample with that probability, on all channels.
"""
import random
import socket
import threading
import time

MODES = ("block", "saturate", "noise")


class Impairments:
    def __init__(self):
        self.noise_p = 0.0
        self._modes = {}  # channel index -> [mode, ticks left or None = hold]
        self._lock = threading.Lock()

    def interfere(self, channel, mode, ticks=None):
        with self._lock:
            if mode in MODES:
                self._modes[channel] = [mode, ticks]
            else:
                self._modes.pop(channel, None)

    def interference(self):
        with self._lock:
            return {ch: m for ch, (m, _) in self._modes.items()}

    def impair(self, rows):
        rows = [list(r) for r in rows]
        with self._lock:
            for ch, entry in list(self._modes.items()):
                mode, left = entry
                if ch >= len(rows):
                    continue
                n = len(rows[ch])
                if mode == "block":
                    rows[ch] = [0] * n
                elif mode == "saturate":
                    rows[ch] = [1] * n
                else:
                    rows[ch] = [random.randint(0, 1) for _ in range(n)]
                if left is not None:
                    entry[1] = left - 1
                    if entry[1] <= 0:
                        del self._modes[ch]
        if self.noise_p:
            rows = [[s ^ (random.random() < self.noise_p) for s in r] for r in rows]
        return rows


class SimPhy(Impairments):
    kind = "sim"

    def __init__(self, channels, samples, hz, rx_port, tx_port, host="127.0.0.1"):
        super().__init__()
        self.channels, self.samples, self.hz = channels, samples, hz
        self.peer = (host, tx_port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((host, rx_port))
        self.on_symbols = None

    def start(self):
        threading.Thread(target=self._rx_loop, daemon=True).start()

    def send_symbols(self, ticks):
        period = 1.0 / self.hz
        t_next = time.monotonic()
        for rows in ticks:
            self.sock.sendto(bytes(s for r in rows for s in r), self.peer)
            t_next += period
            delay = t_next - time.monotonic()
            if delay > 0:
                time.sleep(delay)

    def _rx_loop(self):
        while True:
            data, _ = self.sock.recvfrom(256)
            k = self.samples
            rows = [list(data[i:i + k]) for i in range(0, self.channels * k, k)]
            # rows is still the clean signal here: the scope shows it as "sent"
            self.on_symbols(self.impair(rows), time.monotonic(), rows)
