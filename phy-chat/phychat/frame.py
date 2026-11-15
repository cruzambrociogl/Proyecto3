"""Physical-layer Frame: SYN -> SFD -> Control -> DATA -> CRC -> [SEQ].

Fields are serialized MSB-first and spread across the data lanes tick by
tick: on tick i, lane j carries bit i*lanes + j. The clock channel is not a
lane; it is the strobe that tells the receiver when to sample the lanes.
Each section (SYN, SFD, body) starts on a tick boundary and is zero-padded
to a whole number of ticks.
"""
from collections import deque

CTRL_DATA = 0x1
CTRL_ACK = 0x2
CTRL_NACK = 0x3
CTRL_START = 0x4  # DATA = encoding id
CTRL_END = 0x5    # DATA = message length mod 256
CTRL_PING = 0x6   # heartbeat + hello: DATA = sender's CRC variant id << 6
CTRL_PONG = 0x7   # answer to PING, same DATA layout
CTRL_NAMES = {CTRL_DATA: "DATA", CTRL_ACK: "ACK", CTRL_NACK: "NACK",
              CTRL_START: "START", CTRL_END: "END", CTRL_PING: "PING", CTRL_PONG: "PONG"}

SYN_TICKS = 4       # every lane toggles 1,0,1,0 so each medium settles
SFD = 0xB3          # 1011 0011
SFD_BITS = 8
BODY_BITS = 24      # Control 4 + DATA 8 + CRC 8 + SEQ 4


def to_bits(value, width):
    return [(value >> (width - 1 - i)) & 1 for i in range(width)]


def from_bits(bits):
    v = 0
    for b in bits:
        v = (v << 1) | b
    return v


def _pad(bits, lanes):
    return bits + [0] * ((-len(bits)) % lanes)


def _chunk(bits, lanes):
    return [tuple(bits[i:i + lanes]) for i in range(0, len(bits), lanes)]


def syn_ticks(lanes):
    return [tuple([1 - k % 2] * lanes) for k in range(SYN_TICKS)]


def sfd_ticks(lanes):
    return _chunk(_pad(to_bits(SFD, SFD_BITS), lanes), lanes)


def ticks_per_frame(lanes):
    return SYN_TICKS + len(sfd_ticks(lanes)) + -(-BODY_BITS // lanes)


class Frame:
    def __init__(self, ctrl, data=0, seq=0, crc=0):
        self.ctrl = ctrl & 0xF
        self.data = data & 0xFF
        self.seq = seq & 0xF
        self.crc = crc & 0xFF

    def crc_input(self):
        # CRC covers Control, SEQ and DATA, packed as two bytes
        return bytes([(self.ctrl << 4) | self.seq, self.data])

    def sealed(self, crc8):
        return Frame(self.ctrl, self.data, self.seq, crc8.compute(self.crc_input()))

    def crc_ok(self, crc8):
        return self.crc == crc8.compute(self.crc_input())

    def body_bits(self):
        return (to_bits(self.ctrl, 4) + to_bits(self.data, 8)
                + to_bits(self.crc, 8) + to_bits(self.seq, 4))

    @classmethod
    def from_body_bits(cls, bits):
        return cls(ctrl=from_bits(bits[0:4]), data=from_bits(bits[4:12]),
                   crc=from_bits(bits[12:20]), seq=from_bits(bits[20:24]))

    def ticks(self, lanes):
        return syn_ticks(lanes) + sfd_ticks(lanes) + _chunk(_pad(self.body_bits(), lanes), lanes)

    @property
    def name(self):
        return CTRL_NAMES.get(self.ctrl, "0x%X" % self.ctrl)

    def describe(self):
        b = "".join(map(str, self.body_bits()))
        return {
            "type": self.name, "ctrl": self.ctrl, "seq": self.seq,
            "data": self.data, "crc": self.crc,
            "bits": {"syn": "10" * (SYN_TICKS // 2), "sfd": format(SFD, "08b"),
                     "ctrl": b[0:4], "data": b[4:12], "crc": b[12:20], "seq": b[20:24]},
        }


class Deframer:
    """Receiver side: hunts for SYN tail + SFD, then collects the fixed-size body.

    A gap in the clock longer than gap_s abandons a half-received frame, so a
    transmitter that stops mid-frame cannot poison the next one.
    """

    def __init__(self, lanes, gap_s=1.0):
        self.lanes = lanes
        self.gap_s = gap_s
        self.pattern = [b for t in syn_ticks(lanes)[-2:] + sfd_ticks(lanes) for b in t]
        self.window = deque(maxlen=len(self.pattern))
        self.body_len = len(_pad([0] * BODY_BITS, lanes))
        self.body = None
        self.last_t = None

    def reset(self):
        self.window.clear()
        self.body = None

    @property
    def receiving(self):
        return self.body is not None

    def push(self, bits, t):
        if self.last_t is not None and t - self.last_t > self.gap_s:
            self.reset()
        self.last_t = t
        if self.body is not None:
            self.body.extend(bits)
            if len(self.body) >= self.body_len:
                frame = Frame.from_body_bits(self.body[:BODY_BITS])
                self.reset()
                return frame
            return None
        self.window.extend(bits)
        if len(self.window) == len(self.pattern) and list(self.window) == self.pattern:
            self.body = []
        return None
