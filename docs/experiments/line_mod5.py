"""v4/v5 math: every channel shows one point of a line, counted mod 5.

A nibble (4 bits) becomes a = nibble // 4, b = nibble % 4. On symbol k,
channel x (1..4) shows the value
    y = a + b*x + hop(k, x)   (mod 5)
Any 2 points rebuild the line, and the other points check it.
Flat mode (y = a + hop) carries only 2 bits but needs a single point.

The hop offset must contain x^2: if it were a line in x, the same reading on
every channel (one lamp flickering on all sensors) could pass as valid data.

Run: python3 docs/experiments/line_mod5.py
"""
import itertools

P = 5
XS = (1, 2, 3, 4)
INV = {1: 1, 2: 3, 3: 2, 4: 4}  # division mod 5 = multiply by the inverse


def hop(k, x):
    return (x * x + k * x + 2 * k) % P


def encode(nib, k):
    a, b = divmod(nib, 4)
    return [(a + b * x + hop(k, x)) % P for x in XS]


def line(p1, p2):
    (x1, y1), (x2, y2) = p1, p2
    b = (y2 - y1) * INV[(x2 - x1) % P] % P
    return (y1 - b * x1) % P, b


def decode(ys, k, correct=True):
    """ys: value per channel, None = dead. -> (nibble or None, outcome)

    correct=False never fixes a lying channel, it only reports it: then 2 liars
    are always detected instead of sometimes "fixed" into wrong data.
    """
    pts = [(x, (y - hop(k, x)) % P) for x, y in zip(XS, ys) if y is not None]
    if len(pts) < 2:
        return None, "lost"
    best = None
    for p1, p2 in itertools.combinations(pts, 2):
        a, b = line(p1, p2)
        on = sum((a + b * x) % P == y for x, y in pts)
        if best is None or on > best[2]:
            best = (a, b, on)
    a, b, on = best
    if a > 3 or b > 3:
        return None, "detected"           # a line, but not one we ever send
    if on == len(pts):
        return 4 * a + b, "ok"
    if correct and len(pts) == 4 and on == 3:
        return 4 * a + b, "fixed"         # one point off the line: that channel lied
    return None, "detected"


def encode_flat(a, k):
    return [(a + hop(k, x)) % P for x in XS]


def decode_flat(ys, k):
    vals = {(y - hop(k, x)) % P for x, y in zip(XS, ys) if y is not None}
    if len(vals) == 1 and min(vals) <= 3:
        return min(vals), "ok"
    return None, "lost" if not vals else "detected"


def check():
    fails = {"2 dead": 0, "1 lying": 0, "1 dead + 1 lying accepted wrong": 0}
    two_liars = {"wrong accepted": 0, "wrong accepted, detect-only": 0, "total": 0}
    for k in range(5):
        for nib in range(16):
            ys = encode(nib, k)
            assert decode(ys, k) == (nib, "ok")
            for dead in itertools.combinations(range(4), 2):
                r = [None if i in dead else y for i, y in enumerate(ys)]
                fails["2 dead"] += decode(r, k)[0] != nib
            for i in range(4):
                for w in range(P):
                    if w == ys[i]:
                        continue
                    r = list(ys)
                    r[i] = w
                    fails["1 lying"] += decode(r, k) != (nib, "fixed")
                    for j in range(4):
                        if j != i:
                            r2 = list(r)
                            r2[j] = None
                            got = decode(r2, k)[0]
                            fails["1 dead + 1 lying accepted wrong"] += got is not None and got != nib
            for i, j in itertools.combinations(range(4), 2):
                for wi in range(P):
                    for wj in range(P):
                        if wi == ys[i] or wj == ys[j]:
                            continue
                        r = list(ys)
                        r[i], r[j] = wi, wj
                        got = decode(r, k)[0]
                        two_liars["total"] += 1
                        two_liars["wrong accepted"] += got is not None and got != nib
                        got = decode(r, k, correct=False)[0]
                        two_liars["wrong accepted, detect-only"] += got is not None and got != nib
    same = [(k, c) for k in range(5) for c in range(P) if decode([c] * 4, k)[0] is not None]
    flat = 0
    for k in range(5):
        for a in range(4):
            ys = encode_flat(a, k)
            for alive in range(4):
                r = [y if i == alive else None for i, y in enumerate(ys)]
                flat += decode_flat(r, k) != (a, "ok")
    flat_same = [(k, c) for k in range(5) for c in range(P) if decode_flat([c] * 4, k)[0] is not None]
    return fails, two_liars, same, flat, flat_same


if __name__ == "__main__":
    print("hop table (rows = symbol k, columns = ch1..ch4):")
    for k in range(3):
        print("  k=%d" % k, [hop(k, x) for x in XS])
    print("'h' = 0x68: symbol 0 sends 6 ->", encode(6, 0), "  symbol 1 sends 8 ->", encode(8, 1))
    fails, two_liars, same, flat, flat_same = check()
    for name, n in fails.items():
        print("failures, %s: %d" % (name, n))
    print("2 liars, no dead: %d of %d end in wrong data accepted (the CRC must catch these)"
          % (two_liars["wrong accepted"], two_liars["total"]))
    print("2 liars, no dead, detect-only decoder: %d of %d wrong accepted"
          % (two_liars["wrong accepted, detect-only"], two_liars["total"]))
    print("same reading on all channels accepted (line mode):", same or "never")
    print("flat mode, only 1 channel alive, failures:", flat)
    print("same reading on all channels accepted (flat mode):", flat_same or "never")
