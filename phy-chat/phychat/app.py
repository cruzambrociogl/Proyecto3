"""Application glue: chat messages <-> presentation <-> link, plus the protocol LOG.

A message travels as START(encoding id), one DATA frame per byte, then
END(length mod 256) so the receiver can tell a complete message apart from
one that lost frames.
"""
import itertools
import json
import queue
import threading
import time
from collections import deque

from . import presentation
from .crc8 import VARIANTS
from .frame import CTRL_DATA, CTRL_END, CTRL_START, SFD, SYN_TICKS, ticks_per_frame
from .link import Link


class EventBus:
    def __init__(self, name, logfile=None, history=600):
        self.name = name
        self.history = deque(maxlen=history)
        self.subscribers = []
        self.lock = threading.Lock()
        self.logfile = open(logfile, "a", encoding="utf-8") if logfile else None

    def emit(self, kind, **fields):
        ev = dict(fields, kind=kind, ts=time.time(), node=self.name)
        with self.lock:
            self.history.append(ev)
            subs = list(self.subscribers)
            if self.logfile:
                self.logfile.write(json.dumps(ev, ensure_ascii=False) + "\n")
                self.logfile.flush()
        for q in subs:
            q.put(ev)

    def subscribe(self):
        q = queue.Queue()
        with self.lock:
            backlog = list(self.history)
            self.subscribers.append(q)
        return q, backlog

    def unsubscribe(self, q):
        with self.lock:
            if q in self.subscribers:
                self.subscribers.remove(q)


class ChatNode:
    def __init__(self, name, phy, crc_name="SMBUS", encoding="utf-8", logfile=None):
        self.name = name
        self.phy = phy
        self.bus = EventBus(name, logfile)
        self.encoding = presentation.ENCODING_IDS[encoding]
        self.link = Link(phy, VARIANTS[crc_name], self.bus.emit, self._on_payload)
        self.outbox = queue.Queue()
        self._ids = itertools.count(1)
        self._rx = None  # message being received: {"dec", "text", "count"}

    def start(self):
        if hasattr(self.phy, "on_health"):
            self.phy.on_health = lambda ch, h: self.bus.emit("channel", channel=ch, health=h)
        self.link.start()
        threading.Thread(target=self._send_loop, daemon=True).start()
        self.bus.emit("info", msg="Nodo %s listo: PHY=%s, coding=%s, canales %s, %g Hz, CRC-8/%s"
                      % (self.name, self.phy.kind, self._coding(), "+".join(self._channels()),
                         self.phy.hz, self.link.crc8.name))

    def _coding(self):
        return self.phy.code.name if hasattr(self.phy, "code") else "plain"

    def _channels(self):
        if hasattr(self.phy, "code"):
            return self.phy.code.channels
        return ["CLK"] + ["D%d" % i for i in range(self.phy.lanes)]

    def interfere(self, channel, mode, ticks=None):
        self.phy.interfere(channel, mode, ticks)
        self.bus.emit("interfere", channel=channel, mode=mode, ticks=ticks)

    # --- config ---------------------------------------------------------

    def state(self):
        lanes = self.phy.lanes
        tpf = ticks_per_frame(lanes)
        return {
            "name": self.name, "phy": self.phy.kind, "lanes": lanes, "hz": self.phy.hz,
            "crc": self.link.crc8.name, "crc_params": self.link.crc8.describe(),
            "crc_variants": list(VARIANTS), "encoding": presentation.ENCODINGS[self.encoding][0],
            "encodings": [{"id": n, "label": label} for n, label in presentation.ENCODINGS.values()],
            "frame": {"syn_ticks": SYN_TICKS, "sfd": "0x%02X" % SFD, "ticks": tpf,
                      "seconds": tpf / float(self.phy.hz)},
            "noise_p": getattr(self.phy, "noise_p", None),
            "stats": dict(self.link.stats, **getattr(self.phy, "stats", {})),
            "link": self.link.status(),
            "coding": self._coding(), "channels": self._channels(),
            "interference": self.phy.interference() if hasattr(self.phy, "interference") else None,
            "health": self.phy.health() if hasattr(self.phy, "health") else None,
            "scope": getattr(self.phy, "scope", None),
            "read_points": self.phy.code.read_points if hasattr(self.phy, "code") else None,
        }

    def configure(self, crc=None, encoding=None, noise_p=None, scope=None):
        if crc:
            self.link.crc8 = VARIANTS[crc]
            self.link.announce()  # tell the peer right away
        if encoding:
            self.encoding = presentation.ENCODING_IDS[encoding]
        if noise_p is not None and hasattr(self.phy, "noise_p"):
            self.phy.noise_p = float(noise_p)
        if scope is not None and hasattr(self.phy, "scope"):
            self.phy.scope = bool(scope)
        self.bus.emit("config", crc=self.link.crc8.name,
                      encoding=presentation.ENCODINGS[self.encoding][0],
                      noise_p=getattr(self.phy, "noise_p", None))

    # --- send -----------------------------------------------------------

    def send(self, text):
        msg_id = next(self._ids)
        chars = presentation.encode_chars(text, self.encoding)
        self.bus.emit("chat_out", id=msg_id, text=text,
                      encoding=presentation.ENCODINGS[self.encoding][0],
                      chars=[{"ch": c, "bytes": ["%02X" % b for b in bs]} for c, bs in chars])
        self.outbox.put((msg_id, self.encoding, b"".join(bs for _, bs in chars)))
        return msg_id

    def _send_loop(self):
        while True:
            msg_id, enc, payload = self.outbox.get()
            t0 = time.monotonic()
            frames = [(CTRL_START, enc)] + [(CTRL_DATA, b) for b in payload] + [(CTRL_END, len(payload) & 0xFF)]
            retx, ok = 0, True
            for i, (ctrl, data) in enumerate(frames):
                ok, n = self.link.send_reliable(ctrl, data)
                retx += n
                self.bus.emit("chat_progress", id=msg_id, done=i + 1, total=len(frames))
                if not ok:
                    break
            self.bus.emit("chat_status", id=msg_id, ok=ok, retx=retx, frames=len(frames),
                          seconds=round(time.monotonic() - t0, 2))

    # --- receive --------------------------------------------------------

    def _on_payload(self, ctrl, data):
        if ctrl == CTRL_START:
            if data not in presentation.ENCODINGS:
                self.bus.emit("error", msg="START con encoding desconocido: %d" % data)
                self._rx = None
                return
            if self._rx is not None:
                self.bus.emit("error", msg="Mensaje incompleto descartado (llegó un nuevo START)")
            self._rx = {"enc": data, "dec": presentation.decoder(data), "text": "", "count": 0}
            self.bus.emit("chat_partial", text="", encoding=presentation.ENCODINGS[data][0])
        elif self._rx is None:
            self.bus.emit("error", msg="Frame %s fuera de un mensaje" % ("DATA" if ctrl == CTRL_DATA else "END"))
        elif ctrl == CTRL_DATA:
            self._rx["count"] += 1
            self._rx["text"] += self._rx["dec"].feed(data)
            self.bus.emit("chat_partial", text=self._rx["text"], byte="%02X" % data,
                          encoding=presentation.ENCODINGS[self._rx["enc"]][0])
        elif ctrl == CTRL_END:
            rx, self._rx = self._rx, None
            text = rx["text"] + rx["dec"].flush()
            complete = (rx["count"] & 0xFF) == data
            self.bus.emit("chat_in", text=text, complete=complete, bytes=rx["count"],
                          encoding=presentation.ENCODINGS[rx["enc"]][0])
