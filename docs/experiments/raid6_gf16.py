"""v3 (on hold): two parity lanes over GF(16), RAID-6 style.

Each data lane carries a 4-bit number spread over 4 ticks. Two helper lanes:
  P = D0 + D1        Q = D0 + 2*D1
where + is XOR and * is GF(16) multiplication (polynomial x^4 + x + 1).
Any 2 of D0, D1, P, Q rebuild the byte. On hold because D0 and D1 still carry
different data, which the professor calls serial.

Run: python3 docs/experiments/raid6_gf16.py
"""


def mul(a, b):
    r = 0
    for _ in range(4):
        if b & 1:
            r ^= a
        b >>= 1
        a <<= 1
        if a & 0x10:
            a ^= 0x13  # x^4 + x + 1
    return r


INV = {a: next(b for b in range(1, 16) if mul(a, b) == 1) for a in range(1, 16)}


def encode(d0, d1):
    return d0, d1, d0 ^ d1, d0 ^ mul(2, d1)


def recover(lost, D0, D1, P, Q):
    """Closed formulas for each pair of lost lanes -> (d0, d1)."""
    return {
        ("D0", "D1"): lambda: (P ^ mul(INV[3], P ^ Q), mul(INV[3], P ^ Q)),
        ("D0", "P"): lambda: (Q ^ mul(2, D1), D1),
        ("D0", "Q"): lambda: (P ^ D1, D1),
        ("D1", "P"): lambda: (D0, mul(INV[2], Q ^ D0)),
        ("D1", "Q"): lambda: (D0, P ^ D0),
        ("P", "Q"): lambda: (D0, D1),
    }[lost]()


if __name__ == "__main__":
    print("inverse of 2 =", INV[2], " inverse of 3 =", INV[3])
    print("'h' = 0x68 -> D0, D1, P, Q =", encode(0x6, 0x8))
    bad = 0
    pairs = [("D0", "D1"), ("D0", "P"), ("D0", "Q"), ("D1", "P"), ("D1", "Q"), ("P", "Q")]
    for d0 in range(16):
        for d1 in range(16):
            for lost in pairs:
                bad += recover(lost, *encode(d0, d1)) != (d0, d1)
    print("wrong recoveries: %d of %d" % (bad, 256 * len(pairs)))
