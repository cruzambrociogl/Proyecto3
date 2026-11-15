"""Data link layer: CRC check, ACK/NACK, stop-and-wait retransmission, link health.

One TX thread owns the physical transmitter. ACK/NACK/PONG frames jump the
queue so the peer is never kept waiting behind our own data. SEQ (mod 16)
lets the receiver drop duplicates when an ACK is lost and the sender
retransmits.

Link health:
  - PING/PONG heartbeat while idle. Both carry the sender's CRC variant
    (hello), and both are checked with the fixed MGMT CRC so a node can read
    its peer's settings even when they differ from its own.
  - Status: connected (we hear the peer and it answers us), rx_only (we hear
    it but it does not answer: our TX path or its RX is broken), down.
  - Peer clock: the receiver times the CLK edges, so timeouts follow the
    peer's real tick rate instead of assuming it matches ours.
"""
import itertools
import queue
import threading
import time
from collections import deque

from .crc8 import MGMT, VARIANT_IDS
from .frame import (CTRL_ACK, CTRL_NACK, CTRL_PING, CTRL_PONG, CTRL_START,
                    Deframer, Frame, ticks_per_frame)

PRIO_CONTROL = 0
PRIO_DATA = 1
VARIANT_NAMES = {i: name for name, i in VARIANT_IDS.items()}


class Link:
    MAX_RETRIES = 8

    def __init__(self, phy, crc8, emit, on_payload):
        self.phy = phy
        self.crc8 = crc8
        self.emit = emit              # emit(kind, **fields) -> protocol LOG
        self.on_payload = on_payload  # on_payload(ctrl, data) for valid, new frames
        self.txq = queue.PriorityQueue()
        self._order = itertools.count()
        self.replies = queue.Queue()
        self.tx_seq = 0
        self.rx_last_seq = None
        self.deframer = Deframer(phy.lanes, gap_s=self._gap_for(phy.hz))
        self.stats = dict(tx=0, rx=0, crc_err=0, ack_tx=0, nack_tx=0,
                          ack_rx=0, nack_rx=0, retx=0, dup=0, failed=0, ping=0, pong=0)
        # link health
        self.last_tx = 0.0
        self.last_heard = None      # any valid frame from the peer
        self.last_answered = None   # ACK or PONG: proof our frames reach the peer
        self.peer_crc = None
        self._tick_t = None
        self._tick_dts = deque(maxlen=64)
        self._status = None
        phy.on_tick = self._on_tick

    def start(self):
        threading.Thread(target=self._tx_loop, daemon=True).start()
        threading.Thread(target=self._health_loop, daemon=True).start()
        self.phy.start()

    # --- timing ---------------------------------------------------------

    @staticmethod
    def _gap_for(hz):
        return max(0.25, 4.0 / hz)

    def peer_hz(self):
        """Median interval between received CLK edges (idle gaps are the minority)."""
        if len(self._tick_dts) < 8:
            return None
        dt = sorted(self._tick_dts)[len(self._tick_dts) // 2]
        return 1.0 / dt if dt > 0 else None

    def frame_time(self, hz=None):
        return ticks_per_frame(self.phy.lanes) / float(hz or self.phy.hz)

    def peer_frame_time(self):
        return self.frame_time(self.peer_hz())

    def ping_interval(self):
        return max(1.0, 3 * self.frame_time())

    def alive_window(self):
        peer_ping = max(1.0, 3 * self.peer_frame_time())
        return 2.5 * max(self.ping_interval(), peer_ping) + 0.5

    # --- transmit -------------------------------------------------------

    def _enqueue(self, prio, frame, note=""):
        sent = threading.Event()
        self.txq.put((prio, next(self._order), frame, note, sent))
        return sent

    def _tx_loop(self):
        while True:
            _, _, frame, note, sent = self.txq.get()
            self.emit("tx", frame=self._describe(frame), note=note)
            self.phy.send_ticks(frame.ticks(self.phy.lanes))
            self.stats["tx"] += 1
            self.last_tx = time.monotonic()
            sent.set()

    def _mgmt(self, ctrl):
        return Frame(ctrl, VARIANT_IDS[self.crc8.name] << 6).sealed(MGMT)

    def announce(self):
        """Send a PING now (startup, settings changed) instead of waiting for the heartbeat."""
        self._enqueue(PRIO_DATA, self._mgmt(CTRL_PING), "hello")

    def send_reliable(self, ctrl, data):
        """Blocks until ACKed or retries run out. Returns (ok, retransmissions)."""
        seq = self.tx_seq
        frame = Frame(ctrl, data, seq).sealed(self.crc8)
        while not self.replies.empty():
            self.replies.get_nowait()
        for attempt in range(self.MAX_RETRIES + 1):
            note = "retx #%d" % attempt if attempt else ""
            self._enqueue(PRIO_DATA, frame, note).wait()
            # the peer may be mid-frame before its ACK, and both go at the peer's clock
            timeout = 2 * self.peer_frame_time() + 0.2
            reply = self._wait_reply(seq, time.monotonic() + timeout)
            if reply == "ack":
                self.tx_seq = (seq + 1) % 16
                return True, attempt
            self.stats["retx"] += 1
            self.emit("retx", seq=seq, reason=reply, attempt=attempt + 1)
        self.stats["failed"] += 1
        self.emit("error", msg="Frame seq=%d descartado tras %d reintentos" % (seq, self.MAX_RETRIES))
        self.tx_seq = (seq + 1) % 16
        return False, self.MAX_RETRIES

    def _wait_reply(self, seq, deadline):
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                return "timeout"
            try:
                reply = self.replies.get(timeout=left)
            except queue.Empty:
                return "timeout"
            if reply.ctrl == CTRL_NACK:
                return "nack"
            if reply.seq == seq:
                return "ack"
            # ACK for an older seq (late duplicate): keep waiting

    # --- health ---------------------------------------------------------

    def _health_loop(self):
        self.announce()
        while True:
            time.sleep(0.25)
            if self.txq.empty() and time.monotonic() - self.last_tx > self.ping_interval():
                self._enqueue(PRIO_DATA, self._mgmt(CTRL_PING))
            st = self.status()
            key = (st["state"], st["peer_crc"])
            if key != self._status:
                self._status = key
                self.emit("link", **st)

    def status(self):
        now = time.monotonic()
        window = self.alive_window()
        heard = self.last_heard is not None and now - self.last_heard < window
        answered = self.last_answered is not None and now - self.last_answered < window
        hz = self.peer_hz()
        return {
            "state": "connected" if heard and answered else "rx_only" if heard else "down",
            "last_heard_s": None if self.last_heard is None else round(now - self.last_heard, 1),
            "peer_hz": None if hz is None else round(hz, 1),
            "peer_crc": self.peer_crc,
            "crc_match": self.peer_crc is None or self.peer_crc == self.crc8.name,
        }

    # --- receive --------------------------------------------------------

    def _on_tick(self, bits, t):
        if self._tick_t is not None:
            self._tick_dts.append(t - self._tick_t)
            if len(self._tick_dts) % 16 == 0:
                hz = self.peer_hz()
                if hz:
                    self.deframer.gap_s = self._gap_for(hz)
        self._tick_t = t
        frame = self.deframer.push(bits, t)
        if frame is not None:
            self._on_frame(frame)

    def _crc_for(self, frame):
        return MGMT if frame.ctrl in (CTRL_PING, CTRL_PONG) else self.crc8

    def _describe(self, frame):
        desc = frame.describe()
        desc["crc_name"] = self._crc_for(frame).name
        if frame.ctrl in (CTRL_PING, CTRL_PONG):
            desc["peer_crc"] = VARIANT_NAMES.get(frame.data >> 6)
        return desc

    def _on_frame(self, frame):
        crc = self._crc_for(frame)
        ok = frame.crc_ok(crc)
        self.stats["rx"] += 1
        desc = self._describe(frame)
        desc["crc_expected"] = crc.compute(frame.crc_input())
        report = self.phy.frame_report() if hasattr(self.phy, "frame_report") else None
        self.emit("rx", frame=desc, crc_ok=ok, coding=report)
        if not ok:
            self.stats["crc_err"] += 1
            self.stats["nack_tx"] += 1
            self._enqueue(PRIO_CONTROL, Frame(CTRL_NACK, 0, frame.seq).sealed(self.crc8), "CRC error")
            return
        self.last_heard = time.monotonic()
        if frame.ctrl in (CTRL_PING, CTRL_PONG):
            self.peer_crc = VARIANT_NAMES.get(frame.data >> 6)
            if frame.ctrl == CTRL_PING:
                self.stats["ping"] += 1
                self._enqueue(PRIO_CONTROL, self._mgmt(CTRL_PONG))
            else:
                self.stats["pong"] += 1
                self.last_answered = self.last_heard
            return
        if frame.ctrl in (CTRL_ACK, CTRL_NACK):
            self.stats["ack_rx" if frame.ctrl == CTRL_ACK else "nack_rx"] += 1
            self.last_answered = self.last_heard
            self.replies.put(frame)
            return
        self.stats["ack_tx"] += 1
        self._enqueue(PRIO_CONTROL, Frame(CTRL_ACK, 0, frame.seq).sealed(self.crc8))
        # START always opens a fresh message, so a restarted peer is never mistaken for a duplicate
        if frame.seq == self.rx_last_seq and frame.ctrl != CTRL_START:
            self.stats["dup"] += 1
            self.emit("dup", seq=frame.seq)
            return
        if self.rx_last_seq is not None:
            self.last_answered = self.last_heard  # the peer moved on, so our last ACK reached it
        self.rx_last_seq = frame.seq
        self.on_payload(frame.ctrl, frame.data)
