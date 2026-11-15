#!/usr/bin/env python3
"""Check every TX -> RX jumper/medium in a pin map before running the chat.

  python3 tools/gpio_selftest.py config/bbb_loopback.json

For each side, drives each TX pin 0/1 and reads every RX pin, so a swapped
or missing wire shows up as the wrong RX pin following.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from phychat.phy_gpio import Pin  # noqa: E402


def main():
    cfg = json.load(open(sys.argv[1]))
    # A's TX feeds B's RX and vice versa
    links = [("A", "B"), ("B", "A")]
    all_ok = True
    for tx_side, rx_side in links:
        tx = cfg[tx_side]["tx"]
        rx = cfg[rx_side]["rx"]
        tx_pins = [tx["clk"]] + tx["data"]
        rx_pins = [rx["clk"]] + rx["data"]
        outs = [Pin(p, "out") for p in tx_pins]
        ins = [Pin(p, "in") for p in rx_pins]
        print("%s.TX -> %s.RX" % (tx_side, rx_side))
        for i, out in enumerate(outs):
            name = "CLK" if i == 0 else "D%d" % (i - 1)
            readings = []
            for level in (1, 0, 1, 0):
                for o in outs:
                    o.write(0)
                out.write(level)
                time.sleep(0.01)
                readings.append([p.read() for p in ins])
            expected = [[lvl if j == i else 0 for j in range(len(ins))] for lvl in (1, 0, 1, 0)]
            ok = readings == expected
            all_ok &= ok
            print("  %-4s %-6s -> %-6s %s" % (name, tx_pins[i], rx_pins[i], "OK" if ok else "FAIL %s" % readings))
        for o in outs:
            o.write(0)
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
