"""Line coding: how one tick of data bits becomes samples on the physical channels.

Sits between the link and the medium (the role of Ethernet's PCS). Each tick
the medium carries `samples` samples per channel.

plain: the original scheme. CLK + N data lanes; a lane is a level (on = 1)
       read at the CLK edge. A blocked or flooded lane looks like valid data.

fec:   the design in docs/diseno_canales.xlsx. CLK + N data lanes + P.
       1. Symbol: 4 samples per tick, bit 1 = 0011, bit 0 = 1100 (a transition
          mid-tick), CLK = 1100. Any other pattern means the lane is erased (E).
       2. Parity: P = XOR of the data lanes. One erased lane = XOR of the rest.
       3. History: a lane erased in the last K ticks is suspect; if the parity
          fails with nothing erased, the suspect lane is flipped.
       The link's CRC-8 + ACK/NACK still checks every frame after correction.
"""
from collections import deque

from .frame import ticks_per_frame

CLK = (1, 1, 0, 0)
SYMBOL = {1: (0, 0, 1, 1), 0: (1, 1, 0, 0)}
BIT = {v: k for k, v in SYMBOL.items()}

# per-tick outcome, same names as the Excel "Estado" column
OK, OK_NO_PARITY, FIXED, FIXED_SUSPECT, DETECTED, LOST, NO_TIMING = (
    "ok", "ok_no_parity", "fixed", "fixed_suspect", "detected", "lost", "no_timing")


class PlainCode:
    name = "plain"
    samples = 2
    read_points = [0]  # samples the receiver actually looks at (the CLK edge)

    def __init__(self, lanes):
        self.lanes = lanes
        self.channels = ["CLK"] + ["D%d" % i for i in range(lanes)]

    def encode(self, bits):
        return [(1, 0)] + [(b, b) for b in bits]

    def decode(self, rows):
        """-> (bits or None if the tick is lost, outcome, per-channel bad flag or None if unknowable)"""
        clk_ok = tuple(rows[0]) == (1, 0)
        bad = [not clk_ok] + [None] * self.lanes  # a plain lane can't tell it is broken
        self.read = [r[0] for r in rows[1:]]
        if not clk_ok:
            return None, NO_TIMING, bad
        return [r[0] for r in rows[1:]], OK, bad


class FecCode:
    name = "fec"
    samples = 4
    read_points = [0, 1, 2, 3]

    def __init__(self, lanes, history=8):
        self.lanes = lanes
        self.history = history
        self.channels = ["CLK"] + ["D%d" % i for i in range(lanes)] + ["P"]
        self.tick = 0
        self.last_erased = {}  # lane index (data + P) -> tick it was last erased

    def encode(self, bits):
        p = 0
        for b in bits:
            p ^= b
        return [CLK] + [SYMBOL[b] for b in list(bits) + [p]]

    def suspects(self):
        return [i for i, t in self.last_erased.items() if self.tick - t <= self.history]

    def decode(self, rows):
        self.tick += 1
        clk_ok = tuple(rows[0]) == CLK
        vals = [BIT.get(tuple(r)) for r in rows[1:]]  # None = erased
        self.read = list(vals)  # as read, before any correction (for the scope)
        erased = [i for i, v in enumerate(vals) if v is None]
        bad = [not clk_ok] + [v is None for v in vals]
        if not clk_ok and len(erased) == len(vals):
            return None, NO_TIMING, bad  # no edges on any channel: the tick itself is lost
        suspects = self.suspects()  # from earlier ticks only
        for i in erased:
            self.last_erased[i] = self.tick
        parity_lane = len(vals) - 1
        if len(erased) >= 2:
            outcome = LOST
            vals = [v or 0 for v in vals]  # best guess; the CRC will reject it
        elif len(erased) == 1:
            i = erased[0]
            vals[i] = 0
            for j, v in enumerate(vals):
                if j != i:
                    vals[i] ^= v
            outcome = OK_NO_PARITY if i == parity_lane else FIXED
        else:
            s = 0
            for v in vals:
                s ^= v
            if s == 0:
                outcome = OK
            elif len(suspects) == 1:
                vals[suspects[0]] ^= 1
                outcome = FIXED_SUSPECT
            else:
                outcome = DETECTED
        return vals[:self.lanes], outcome, bad


CODES = {"plain": PlainCode, "fec": FecCode}


class CodedPhy:
    """What the link sees as its PHY: data bits per tick in, data bits per tick out.

    Underneath, `medium` moves per-channel samples (SimPhy or a test loop).
    Also tracks each channel's health so the UI can show which light is down.
    """
    HEALTH_WINDOW = 24

    def __init__(self, medium, code):
        self.medium = medium
        self.code = code
        self.lanes = code.lanes
        self.hz = medium.hz
        self.kind = medium.kind
        self.on_tick = None
        self.stats = dict(fec_fixed=0, fec_suspect=0, fec_detected=0, fec_lost=0, clk_lost=0, ticks_lost=0)
        self._bad = [deque(maxlen=self.HEALTH_WINDOW) for _ in code.channels]
        self._health = [None] * len(code.channels)
        self._report = self._new_report()
        self.on_health = None  # on_health(channel, health) when a channel changes state
        self.scope = False     # record every tick of each received frame for the UI
        self._trace = deque(maxlen=ticks_per_frame(code.lanes))  # a frame is the last N ticks
        medium.on_symbols = self._on_symbols

    @property
    def noise_p(self):
        return self.medium.noise_p

    @noise_p.setter
    def noise_p(self, p):
        self.medium.noise_p = p

    def start(self):
        self.medium.start()

    def send_ticks(self, ticks):
        self.medium.send_symbols([self.code.encode(list(t)) for t in ticks])

    def interfere(self, channel, mode, ticks=None):
        self.medium.interfere(self.code.channels.index(channel), mode, ticks)

    def interference(self):
        modes = self.medium.interference()
        return {ch: modes.get(i) for i, ch in enumerate(self.code.channels)}

    def health(self):
        return dict(zip(self.code.channels, self._health))

    @staticmethod
    def _new_report():
        return {"ticks": 0, "fixed": 0, "suspect": 0, "detected": 0, "lost": 0, "clk_lost": 0, "lanes": []}

    def frame_report(self):
        """What the coding layer did since the last frame (attached to the LOG's rx entry)."""
        r, self._report = self._report, self._new_report()
        if self.scope:
            r["trace"] = list(self._trace)
        self._trace.clear()
        return r

    def _on_symbols(self, rows, t, sent=None):
        """rows: samples as received. sent: the same tick before interference (simulator only)."""
        bits, outcome, bad = self.code.decode(rows)
        self._track(bad)
        rep = self._report
        rep["ticks"] += 1
        for i, b in enumerate(bad):
            if b and self.code.channels[i] not in rep["lanes"]:
                rep["lanes"].append(self.code.channels[i])
        if bad[0]:
            rep["clk_lost"] += 1
            self.stats["clk_lost"] += 1
        key = {FIXED: "fixed", FIXED_SUSPECT: "suspect", DETECTED: "detected", LOST: "lost"}.get(outcome)
        if key:
            rep[key] += 1
            self.stats["fec_" + key] += 1
        if bits is None:
            self.stats["ticks_lost"] += 1
            return
        if self.scope:
            fmt = lambda rs: ["".join(map(str, r)) for r in rs]
            self._trace.append({"rx": fmt(rows), "tx": fmt(sent) if sent else None,
                                "read": self.code.read, "bits": bits, "out": outcome})
        self.on_tick(bits, t)

    def _track(self, bad):
        for i, b in enumerate(bad):
            if b is None:
                continue
            self._bad[i].append(b)
            n = sum(self._bad[i])
            h = "down" if n >= len(self._bad[i]) * 2 // 3 and n >= 4 else "flaky" if n else "ok"
            if h != self._health[i]:
                old, self._health[i] = self._health[i], h
                if self.on_health and old is not None:
                    self.on_health(self.code.channels[i], h)
