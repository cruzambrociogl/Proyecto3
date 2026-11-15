#!/usr/bin/env python3
"""Blink one emitter from a BBB pin, and optionally read a receiver pin at the same time.

  python3 tools/blink.py P8_7                 # 1 Hz (0.5 s on, 0.5 s off), Ctrl+C to stop
  python3 tools/blink.py P8_7 --hz 4
  python3 tools/blink.py P8_7 --rx P8_17      # also prints what the receiver sees

The RX pin is read in the middle of each half period, so the medium has time to settle.
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from phychat.phy_gpio import Pin  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="Blink a TX pin; optionally read an RX pin.")
    ap.add_argument("tx", help="TX pin, e.g. P8_7")
    ap.add_argument("--hz", type=float, default=1.0, help="on/off cycles per second (default 1)")
    ap.add_argument("--rx", help="RX pin to read, e.g. P8_17")
    args = ap.parse_args()

    out = Pin(args.tx, "out")
    inp = Pin(args.rx, "in") if args.rx else None
    quarter = 0.25 / args.hz
    level = 0
    try:
        while True:
            level ^= 1
            out.write(level)
            time.sleep(quarter)
            line = "TX %s=%d" % (args.tx, level)
            if inp:
                seen = inp.read()
                line += "   RX %s=%d  (%s)" % (args.rx, seen, "same" if seen == level else "inverted")
            print(line, flush=True)
            time.sleep(quarter)
    except KeyboardInterrupt:
        pass
    finally:
        out.write(0)


if __name__ == "__main__":
    main()
