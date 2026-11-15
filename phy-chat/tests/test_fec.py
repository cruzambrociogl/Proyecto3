import random
import threading
import unittest

from phychat.app import ChatNode
from phychat.linecode import (DETECTED, FIXED, FIXED_SUSPECT, LOST, NO_TIMING, OK, OK_NO_PARITY,
                              CodedPhy, FecCode, PlainCode)
from phychat.phy_sim import Impairments
from tests.test_stack import until, wait_for

BLOCK, SAT = (0, 0, 0, 0), (1, 1, 1, 1)


def hit(code, bits, lane, pattern):
    rows = code.encode(bits)
    rows[code.channels.index(lane)] = pattern
    return code.decode(rows)


class FecCodeTest(unittest.TestCase):
    """Same rules as the Excel (docs/diseno_canales.xlsx, sheets 2 and 3)."""

    def test_any_single_lane_blocked_or_flooded_is_rebuilt(self):
        for d0 in (0, 1):
            for d1 in (0, 1):
                for lane in ("D0", "D1", "P"):
                    for pattern in (BLOCK, SAT):
                        bits, outcome, _ = hit(FecCode(2), [d0, d1], lane, pattern)
                        self.assertEqual(bits, [d0, d1], (d0, d1, lane, pattern))
                        self.assertEqual(outcome, OK_NO_PARITY if lane == "P" else FIXED)

    def test_clock_lost_data_still_decoded(self):
        bits, outcome, bad = hit(FecCode(2), [1, 0], "CLK", BLOCK)
        self.assertEqual((bits, outcome, bad[0]), ([1, 0], OK, True))

    def test_mimic_without_history_is_detected_not_accepted(self):
        bits, outcome, _ = hit(FecCode(2), [1, 0], "D0", (1, 1, 0, 0))  # looks like a valid 0
        self.assertEqual(outcome, DETECTED)

    def test_mimic_with_history_is_corrected(self):
        code = FecCode(2)
        hit(code, [0, 1], "D0", BLOCK)  # D0 erased on the previous tick -> suspect
        bits, outcome, _ = hit(code, [1, 0], "D0", (1, 1, 0, 0))
        self.assertEqual((bits, outcome), ([1, 0], FIXED_SUSPECT))

    def test_history_expires(self):
        code = FecCode(2, history=3)
        hit(code, [0, 1], "D0", BLOCK)
        for _ in range(3):
            code.decode(code.encode([0, 0]))
        _, outcome, _ = hit(code, [1, 0], "D0", (1, 1, 0, 0))
        self.assertEqual(outcome, DETECTED)

    def test_two_lanes_lost(self):
        code = FecCode(2)
        rows = code.encode([1, 0])
        rows[1] = rows[2] = BLOCK
        self.assertEqual(code.decode(rows)[1], LOST)

    def test_no_edges_anywhere_loses_the_tick(self):
        code = FecCode(2)
        self.assertEqual(code.decode([BLOCK] * 4)[:2], (None, NO_TIMING))

    def test_more_data_lanes(self):
        code = FecCode(4)
        for lane in code.channels[1:]:
            bits, _, _ = hit(code, [1, 0, 1, 1], lane, SAT)
            self.assertEqual(bits, [1, 0, 1, 1], lane)

    def test_plain_cannot_see_a_blocked_lane(self):
        bits, outcome, bad = hit(PlainCode(2), [1, 1], "D1", (0, 0))
        self.assertEqual((bits, outcome, bad[2]), ([1, 0], OK, None))  # wrong bit, and it can't know


class LoopMedium(Impairments):
    """Two media joined in memory; interference is applied at the receiver like SimPhy."""
    kind = "loop"

    def __init__(self, hz=2000):
        super().__init__()
        self.hz = hz
        self.peer = None
        self.on_symbols = None
        self.vt = 0.0
        self.lock = threading.Lock()

    def start(self):
        pass

    def send_symbols(self, ticks):
        with self.lock:
            for rows in ticks:
                self.vt += 1.0 / self.hz
                self.peer.on_symbols(self.peer.impair(rows), self.vt, rows)


def coded_pair(code_cls, lanes=2):
    ma, mb = LoopMedium(), LoopMedium()
    ma.peer, mb.peer = mb, ma
    pa, pb = CodedPhy(ma, code_cls(lanes)), CodedPhy(mb, code_cls(lanes))
    na, nb = ChatNode("A", pa), ChatNode("B", pb)
    na.start()
    nb.start()
    return na, nb, pa, pb


class FecEndToEndTest(unittest.TestCase):
    def send_with(self, code_cls, interference, text="hola ñ€😀", timeout=20):
        na, nb, pa, pb = coded_pair(code_cls)
        for ch, mode in interference:
            pb.interfere(ch, mode)  # B's sensors are disturbed for the whole message
        na.send(text)
        return na, nb, pb, wait_for(na, "chat_status", timeout)

    def test_one_lane_blocked_for_the_whole_message_no_retransmission(self):
        for ch, mode in [("D0", "block"), ("D1", "saturate"), ("P", "block"), ("CLK", "block")]:
            na, nb, pb, status = self.send_with(FecCode, [(ch, mode)])
            self.assertTrue(status["ok"], ch)
            self.assertEqual(status["retx"], 0, ch)
            self.assertEqual(wait_for(nb, "chat_in")["text"], "hola ñ€😀")
            self.assertTrue(until(lambda: pb.health()[ch] == "down"), ch)

    def test_noise_on_one_lane_still_delivers(self):
        random.seed(3)
        na, nb, pb, status = self.send_with(FecCode, [("D1", "noise")])
        self.assertTrue(status["ok"])
        self.assertEqual(wait_for(nb, "chat_in")["text"], "hola ñ€😀")
        self.assertGreater(pb.stats["fec_fixed"], 0)

    def test_scope_trace_shows_sent_received_and_rebuilt(self):
        na, nb, pa, pb = coded_pair(FecCode)
        pb.scope = True
        pb.interfere("D1", "block")
        na.send("h")
        self.assertTrue(wait_for(na, "chat_status")["ok"])
        rx = [e for e in list(nb.bus.history) if e["kind"] == "rx" and e["frame"]["type"] == "DATA"]
        trace = rx[0]["coding"]["trace"]
        self.assertEqual(len(trace), 20)  # SYN 4 + SFD 4 + body 12 ticks
        for tk in trace:
            self.assertEqual(tk["rx"][2], "0000")      # D1 as received: blocked
            self.assertIn(tk["tx"][2], ("0011", "1100"))  # D1 as sent
            self.assertIsNone(tk["read"][1])            # read as erased...
            self.assertEqual(tk["out"], "fixed")        # ...and rebuilt from P

    def test_plain_coding_dies_with_one_lane_blocked(self):
        na, nb, pb, status = self.send_with(PlainCode, [("D1", "saturate")], text="hola")
        self.assertFalse(status["ok"])
        self.assertGreater(na.link.stats["retx"], 0)

    def test_two_lanes_blocked_falls_back_to_crc_nack(self):
        na, nb, pb, status = self.send_with(FecCode, [("D0", "block"), ("D1", "block")], text="h")
        self.assertFalse(status["ok"])
        self.assertGreater(pb.stats["fec_lost"], 0)


if __name__ == "__main__":
    unittest.main()
