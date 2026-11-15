#!/usr/bin/env python3
"""Blink one emitter from a BBB pin, and optionally read a receiver pin at the same time.

  python3 tools/blink.py P8_7                 # 1 Hz (0.5 s on, 0.5 s off); Ctrl+C, q or Enter stops it
  python3 tools/blink.py P8_7 --hz 4
  python3 tools/blink.py P8_7 --rx P8_17      # also prints what the receiver sees

The RX pin is read in the middle of each half period, so the medium has time to settle.
"""
import argparse
import os
import select
import sys
import termios
import time
import tty

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from phychat.phy_gpio import Pin  # noqa: E402

# Ctrl+C is read as a key too: some ssh sessions inherit an interrupt key other than Ctrl+C
STOP_KEYS = (b"\x03", b"q", b"Q", b"\n", b"\r")


def wait(seconds, keys_fd):
    """Sleep; return True if a stop key was pressed meanwhile."""
    if keys_fd is None:
        time.sleep(seconds)
        return False
    end = time.monotonic() + seconds
    while True:
        left = end - time.monotonic()
        if left <= 0:
            return False
        ready, _, _ = select.select([keys_fd], [], [], left)
        if ready and os.read(keys_fd, 1) in STOP_KEYS:
            return True


def main():
    ap = argparse.ArgumentParser(description="Blink a TX pin; optionally read an RX pin.")
    ap.add_argument("tx", help="TX pin, e.g. P8_7")
    ap.add_argument("--hz", type=float, default=1.0, help="on/off cycles per second (default 1)")
    ap.add_argument("--rx", help="RX pin to read, e.g. P8_17")
    args = ap.parse_args()

    out = Pin(args.tx, "out")
    inp = Pin(args.rx, "in") if args.rx else None
    quarter = 0.25 / args.hz
    # without a terminal (e.g. ssh host 'cmd'), stdin may be at EOF and would stop at once
    keys_fd = sys.stdin.fileno() if sys.stdin.isatty() else None
    saved = None
    if keys_fd is not None:
        saved = termios.tcgetattr(keys_fd)
        tty.setcbreak(keys_fd)
        print("Ctrl+C, q or Enter stops it.", flush=True)
    level = 0
    try:
        while True:
            level ^= 1
            out.write(level)
            if wait(quarter, keys_fd):
                break
            line = "TX %s=%d" % (args.tx, level)
            if inp:
                seen = inp.read()
                line += "   RX %s=%d  (%s)" % (args.rx, seen, "same" if seen == level else "inverted")
            print(line, flush=True)
            if wait(quarter, keys_fd):
                break
    except KeyboardInterrupt:
        pass
    finally:
        out.write(0)
        if saved:
            termios.tcsetattr(keys_fd, termios.TCSADRAIN, saved)


if __name__ == "__main__":
    main()
