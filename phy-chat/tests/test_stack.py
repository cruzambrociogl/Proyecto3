import random
import threading
import time
import unittest

from phychat import presentation
from phychat.app import ChatNode
from phychat.crc8 import VARIANTS
from phychat.frame import CTRL_ACK, CTRL_DATA, Deframer, Frame


class CrcTest(unittest.TestCase):
    def test_catalogue_check_values(self):
        for name, crc in VARIANTS.items():
            self.assertEqual(crc.compute(b"123456789"), crc.check, name)

    def test_detects_any_single_bit_error(self):
        crc = VARIANTS["SMBUS"]
        f = Frame(CTRL_DATA, 0x41, 3).sealed(crc)
        bits = f.body_bits()
        for i in range(24):
            flipped = bits[:]
            flipped[i] ^= 1
            self.assertFalse(Frame.from_body_bits(flipped).crc_ok(crc), i)


class Utf8Test(unittest.TestCase):
    SAMPLES = "aZ~ ñé€ 中文 😀𝄞"

    def test_encoder_matches_python(self):
        for ch in self.SAMPLES:
            self.assertEqual(presentation.utf8_encode_char(ch), ch.encode("utf-8"), ch)

    def test_lengths_1_to_4(self):
        lengths = [len(presentation.utf8_encode_char(c)) for c in "Añ€\U0001F600"]
        self.assertEqual(lengths, [1, 2, 3, 4])

    def test_streaming_decoder(self):
        dec = presentation.Utf8Decoder()
        out = "".join(dec.feed(b) for b in self.SAMPLES.encode("utf-8"))
        self.assertEqual(out, self.SAMPLES)

    def test_decoder_rejects_bad_sequences(self):
        for bad in (b"\xc0\xaf", b"\xed\xa0\x80", b"\xf4\x90\x80\x80", b"\x80", b"\xe2\x82A"):
            dec = presentation.Utf8Decoder()
            out = "".join(dec.feed(b) for b in bad) + dec.flush()
            self.assertIn(presentation.REPLACEMENT, out, bad)

    def test_extended_ascii(self):
        chars = presentation.encode_chars("ñÑ", presentation.ENCODING_IDS["cp437"])
        self.assertEqual([bs for _, bs in chars], [b"\xa4", b"\xa5"])


class FrameTest(unittest.TestCase):
    def test_roundtrip_any_lane_count(self):
        crc = VARIANTS["AUTOSAR"]
        # fixed seed: with 2 lanes, junk ending in 11 00 10 right before SYN
        # mimics SYN tail + SFD (1 in 64) and locks 4 ticks early
        rng = random.Random(1)
        for lanes in range(1, 8):
            f = Frame(CTRL_DATA, 0xC3, 9).sealed(crc)
            d = Deframer(lanes)
            junk = [tuple(rng.randint(0, 1) for _ in range(lanes)) for _ in range(5)]
            got = [d.push(list(t), 0.0) for t in junk + f.ticks(lanes)]
            frames = [g for g in got if g]
            self.assertEqual(len(frames), 1, lanes)
            g = frames[0]
            self.assertEqual((g.ctrl, g.data, g.seq, g.crc), (f.ctrl, f.data, f.seq, f.crc))
            self.assertTrue(g.crc_ok(crc))

    def test_gap_abandons_partial_frame(self):
        f = Frame(CTRL_ACK, 0, 1).sealed(VARIANTS["SMBUS"])
        ticks = f.ticks(2)
        d = Deframer(2, gap_s=0.5)
        for t in ticks[:10]:
            d.push(list(t), 0.0)
        self.assertTrue(d.receiving)
        d.push([0, 0], 5.0)
        self.assertFalse(d.receiving)


class LoopPhy:
    """In-memory medium between two nodes, with optional bit flips.

    Delivery is instant; tick timestamps come from a virtual clock at `hz`
    so the receiver's clock measurement sees the configured rate.
    """
    kind = "loop"

    def __init__(self, lanes=2, hz=2000):
        self.lanes, self.hz = lanes, hz
        self.peer = None
        self.on_tick = None
        self.flip_p = 0.0
        self.vt = 0.0
        self.lock = threading.Lock()

    def start(self):
        pass

    def send_ticks(self, ticks):
        with self.lock:
            for t in ticks:
                self.vt += 1.0 / self.hz
                bits = [b ^ (random.random() < self.flip_p) for b in t]
                self.peer.on_tick(bits, self.vt)


def pair(lanes=2, hz_a=2000, hz_b=2000):
    a, b = LoopPhy(lanes, hz_a), LoopPhy(lanes, hz_b)
    a.peer, b.peer = b, a
    na, nb = ChatNode("A", a), ChatNode("B", b)
    na.start()
    nb.start()
    return na, nb, a, b


def wait_for(node, kind, timeout=10):
    q, backlog = node.bus.subscribe()
    for ev in backlog:
        if ev["kind"] == kind:
            return ev
    end = time.time() + timeout
    while time.time() < end:
        try:
            ev = q.get(timeout=0.1)
        except Exception:
            continue
        if ev["kind"] == kind:
            return ev
    raise AssertionError("no %s event" % kind)


class EndToEndTest(unittest.TestCase):
    def test_clean_message_both_directions(self):
        na, nb, _, _ = pair()
        na.send("hola ñ€😀")
        nb.send("¿qué tal?")
        self.assertEqual(wait_for(nb, "chat_in")["text"], "hola ñ€😀")
        self.assertEqual(wait_for(na, "chat_in")["text"], "¿qué tal?")

    def test_noisy_medium_recovers_with_retransmission(self):
        random.seed(7)
        na, nb, a, b = pair(lanes=3)
        a.flip_p = b.flip_p = 0.01
        na.send("ruido!")
        ev = wait_for(nb, "chat_in", timeout=30)
        self.assertEqual(ev["text"], "ruido!")
        self.assertGreater(na.link.stats["retx"], 0)
        self.assertTrue(wait_for(na, "chat_status")["ok"])


def until(cond, timeout=5):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


class HealthTest(unittest.TestCase):
    def test_heartbeat_reports_connected(self):
        na, nb, _, _ = pair()
        self.assertTrue(until(lambda: na.link.status()["state"] == "connected"))
        self.assertTrue(until(lambda: nb.link.status()["state"] == "connected"))
        self.assertEqual(na.link.status()["peer_crc"], "SMBUS")

    def test_crc_mismatch_is_announced(self):
        na, nb, _, _ = pair()
        nb.configure(crc="AUTOSAR")
        self.assertTrue(until(lambda: na.link.peer_crc == "AUTOSAR"))
        self.assertFalse(na.link.status()["crc_match"])
        na.configure(crc="AUTOSAR")
        self.assertTrue(until(lambda: nb.link.status()["crc_match"] and na.link.status()["crc_match"]))

    def test_one_way_link_is_rx_only(self):
        na, nb, a, b = pair()
        self.assertTrue(until(lambda: na.link.status()["state"] == "connected"))
        na.link.last_answered = time.monotonic() - 999  # A's frames stop being answered
        self.assertEqual(na.link.status()["state"], "rx_only")

    def test_different_clock_rates(self):
        na, nb, _, _ = pair(hz_a=50, hz_b=10)
        na.send("rápido")
        nb.send("lento")
        self.assertEqual(wait_for(nb, "chat_in")["text"], "rápido")
        self.assertEqual(wait_for(na, "chat_in")["text"], "lento")
        self.assertAlmostEqual(nb.link.peer_hz(), 50, delta=1)
        self.assertAlmostEqual(na.link.peer_hz(), 10, delta=1)


if __name__ == "__main__":
    unittest.main()
