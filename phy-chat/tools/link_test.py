#!/usr/bin/env python3
"""Send text both ways over two facing light channels on one BBB and check every bit.

  python3 tools/link_test.py
  python3 tools/link_test.py --hz 1 --a "hola" --b "h"
  python3 tools/link_test.py --a-tx P8_7 --a-rx P8_17 --b-tx P8_14 --b-rx P8_10

A's laser (--a-tx) faces B's receiver (--b-rx); B's laser (--b-tx) faces A's receiver (--a-rx).
Aim: both lasers stay on for --aim seconds (default 10) and each receiver shows lit/DARK live.
Step 1, alignment: each laser blinks alone; the facing receiver must follow it and the
other receiver must stay dark. Step 2, data: both sides send their text at the same time,
one bit per period (UTF-8, MSB first); each receiver reads in the middle of the bit.
The receivers are inverting (lit = 0 on the pin); use --no-invert for one that is not.
Ctrl+C, q or Enter stops it.
"""
import argparse
import os
import sys
import termios
import tty

sys.path.insert(0, os.path.dirname(__file__))
from blink import Pin, wait  # noqa: E402


def to_bits(data):
    return [(byte >> (7 - i)) & 1 for byte in data for i in range(8)]


def show(byte):
    ch = chr(byte)
    return "%02X '%s'" % (byte, ch if 32 <= byte < 127 else ".")


def main():
    ap = argparse.ArgumentParser(description="Two-way bit test over facing light channels.")
    ap.add_argument("--a-tx", default="P8_7", help="A's laser (default P8_7)")
    ap.add_argument("--a-rx", default="P8_17", help="A's receiver, faces B's laser (default P8_17)")
    ap.add_argument("--b-tx", default="P8_14", help="B's laser (default P8_14)")
    ap.add_argument("--b-rx", default="P8_10", help="B's receiver, faces A's laser (default P8_10)")
    ap.add_argument("--hz", type=float, default=2.0, help="bits per second (default 2)")
    ap.add_argument("--a", default="hola", help="text A sends to B")
    ap.add_argument("--b", default="CC8!", help="text B sends to A")
    ap.add_argument("--no-invert", action="store_true", help="receivers give 1 when lit")
    ap.add_argument("--aim", type=float, default=10, help="seconds with both lasers on to aim them (default 10, 0 skips)")
    args = ap.parse_args()

    a_tx, b_tx = Pin(args.a_tx, "out"), Pin(args.b_tx, "out")
    a_rx, b_rx = Pin(args.a_rx, "in"), Pin(args.b_rx, "in")
    flip = 0 if args.no_invert else 1

    def lit(pin):
        return pin.read() ^ flip

    half = 0.5 / args.hz
    keys_fd = sys.stdin.fileno() if sys.stdin.isatty() else None
    saved = None
    if keys_fd is not None:
        saved = termios.tcgetattr(keys_fd)
        tty.setcbreak(keys_fd)
        print("Ctrl+C, q or Enter stops it.", flush=True)

    try:
        if args.aim > 0:
            print("\n== Aim: both lasers on for %g s, put each dot on the receiver it faces ==" % args.aim)
            a_tx.write(1)
            b_tx.write(1)
            for k in range(int(args.aim * 2)):
                if wait(0.5, keys_fd):
                    return
                print("  %4.1f s left   A->B: B receiver %-4s   B->A: A receiver %s" % (
                    args.aim - (k + 1) * 0.5, "lit" if lit(b_rx) else "DARK",
                    "lit" if lit(a_rx) else "DARK"), flush=True)
            a_tx.write(0)
            b_tx.write(0)

        print("\n== Step 1: alignment (each laser alone) ==")
        align_ok = True
        for name, laser, other, facing, back in (("A->B", a_tx, b_tx, b_rx, a_rx),
                                                 ("B->A", b_tx, a_tx, a_rx, b_rx)):
            other.write(0)
            for level in (1, 0, 1, 0):
                laser.write(level)
                if wait(half, keys_fd):
                    return
                f, b = lit(facing), lit(back)
                ok = f == level and b == 0
                align_ok &= ok
                print("  %s laser %-3s  facing receiver %-4s  other receiver %-4s  %s" % (
                    name, "on" if level else "off", "lit" if f else "dark", "lit" if b else "dark",
                    "OK" if ok else "FAIL"), flush=True)
                if wait(half, keys_fd):
                    return
        if not align_ok:
            print("  -> alignment failed: check aim, which wire is on which pin, and light from the other laser")

        bits_ab = to_bits(args.a.encode("utf-8"))
        bits_ba = to_bits(args.b.encode("utf-8"))
        n = max(len(bits_ab), len(bits_ba))
        print("\n== Step 2: data both ways at %g bit/s (%d bits, about %d s) ==" % (args.hz, n, round(n / args.hz)))
        got_ab, got_ba = [], []
        err_ab = err_ba = 0
        for i in range(n):
            sa = bits_ab[i] if i < len(bits_ab) else 0
            sb = bits_ba[i] if i < len(bits_ba) else 0
            a_tx.write(sa)
            b_tx.write(sb)
            if wait(half, keys_fd):
                return
            ra, rb = lit(b_rx), lit(a_rx)
            got_ab.append(ra)
            got_ba.append(rb)
            err_ab += (ra != sa) and i < len(bits_ab)
            err_ba += (rb != sb) and i < len(bits_ba)
            line = "  bit %2d   A->B %d->%d %s   B->A %d->%d %s" % (
                i, sa, ra, "ok" if ra == sa else "XX", sb, rb, "ok" if rb == sb else "XX")
            if i % 8 == 7:
                byte_ab = int("".join(map(str, got_ab[-8:])), 2)
                byte_ba = int("".join(map(str, got_ba[-8:])), 2)
                line += "   | bytes: A->B %s  B->A %s" % (show(byte_ab), show(byte_ba))
            print(line, flush=True)
            if wait(half, keys_fd):
                return

        def text(bits, count):
            data = bytes(int("".join(map(str, bits[k:k + 8])), 2) for k in range(0, count, 8))
            return data.decode("utf-8", errors="replace")

        print("\n== Result ==")
        print("  A->B sent %-10r received %-10r bit errors %d/%d" % (
            args.a, text(got_ab, len(bits_ab)), err_ab, len(bits_ab)))
        print("  B->A sent %-10r received %-10r bit errors %d/%d" % (
            args.b, text(got_ba, len(bits_ba)), err_ba, len(bits_ba)))
    except KeyboardInterrupt:
        pass
    finally:
        a_tx.write(0)
        b_tx.write(0)
        if saved:
            termios.tcsetattr(keys_fd, termios.TCSADRAIN, saved)


if __name__ == "__main__":
    main()
