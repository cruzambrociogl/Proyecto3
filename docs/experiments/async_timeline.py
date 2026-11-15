"""v5 timing: channels run on their own, there are no shared windows.

Each symbol is CYCLES cycles of the channel's own frequency (value -> Hz from
that channel's table). The receiver solves symbol k as soon as 2 channels have
delivered their k-th symbol, and confirms it with the 3rd. Values come from
line_mod5 (same line + hop offsets).

Run:
  python3 docs/experiments/async_timeline.py                 # 'h', all alive
  python3 docs/experiments/async_timeline.py hi --dead 2,3   # channels 2 and 3 dead
  python3 docs/experiments/async_timeline.py h --hz 1:1-5 2:10-50
      (channel 1 uses 1..5 Hz, channel 2 uses 10..50 Hz in 5 even steps)
"""
import argparse

from line_mod5 import XS, encode

CYCLES = 2
DT = 0.05  # one character of the drawing, in seconds


def freq_table(spec):
    lo, hi = (float(v) for v in spec.split("-"))
    return [lo + (hi - lo) * v / 4 for v in range(5)]


def nibbles(text):
    for byte in text.encode("utf-8"):
        yield byte >> 4
        yield byte & 0xF


def schedule(text, tables):
    """-> {x: [(start, end, hz, value)]} for every channel."""
    out = {}
    for x in XS:
        t, rows = 0.0, []
        for k, nib in enumerate(nibbles(text)):
            v = encode(nib, k)[x - 1]
            hz = tables[x][v]
            rows.append((t, t + CYCLES / hz, hz, v))
            t += CYCLES / hz
        out[x] = rows
    return out


def draw(rows, width):
    s = ""
    for i in range(width):
        tm = (i + 0.5) * DT
        for a, b, hz, _ in rows:
            if a <= tm < b:
                s += "‾" if ((tm - a) * hz) % 1 < 0.5 else "_"
                break
        else:
            s += " "
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("text", nargs="?", default="h")
    ap.add_argument("--dead", default="", help="channels that never arrive, e.g. 2,3")
    ap.add_argument("--hz", nargs="*", default=[], help="per-channel range, e.g. 2:10-50")
    ap.add_argument("--width", type=int, default=70, help="characters of drawing (1 char = 50 ms)")
    args = ap.parse_args()
    dead = {int(c) for c in args.dead.split(",") if c}
    tables = {x: freq_table("1-5") for x in XS}
    for spec in args.hz:
        ch, rng = spec.split(":")
        tables[int(ch)] = freq_table(rng)

    sched = schedule(args.text, tables)
    print("text %r, %d cycles per symbol, dead: %s" % (args.text, CYCLES, sorted(dead) or "none"))
    for x in XS:  # what the receiver sees: a dead channel is flat (hand over the sensor)
        wave = "_" * args.width if x in dead else draw(sched[x], args.width)
        print("ch%d %s %s" % (x, "DEAD" if x in dead else "    ", wave))
    print()
    n = len(sched[XS[0]])
    total = 0.0
    for k in range(n):
        arrivals = sorted((sched[x][k][1], x) for x in XS if x not in dead)
        cells = "  ".join("ch%d=%d (%.2fs)" % (x, sched[x][k][3], sched[x][k][1]) for x in XS)
        if len(arrivals) < 2:
            print("symbol %d: LOST (fewer than 2 channels)   %s" % (k, cells))
            continue
        solved = arrivals[1][0]
        confirmed = "%.2fs" % arrivals[2][0] if len(arrivals) > 2 else "never (no 3rd point)"
        total = max(total, solved)
        print("symbol %d: solved %.2fs, confirmed %s   %s" % (k, solved, confirmed, cells))
    lockstep = sum(max(sched[x][k][1] - sched[x][k][0] for x in XS) for k in range(n))
    print("\nall symbols solved at %.2fs; if every channel waited for the slowest one: %.2fs"
          % (total, lockstep))


if __name__ == "__main__":
    main()
