"""v6: one byte = one matrix. Rows are ticks (serial), columns are channels (parallel).

            D0   D1   P    Q
  tick 0    d    d    p    q
  tick 1    d    d    p    q
  tick 2    d    d    p    q
  tick 3    d    d    p    q
  tick 4    v    v    v    v

Three families of XOR equations, each must come out even:
  horizontal  P[i] = D0[i] ^ D1[i]                      (checked at every tick)
  diagonal    Q[0] = D0[0] ^ P[1]
              Q[1] = D0[1] ^ D1[0] ^ P[2]
              Q[2] = D0[2] ^ D1[1] ^ P[3]
              Q[3] = D0[3] ^ D1[2]                      (row + diagonal = RDP, the RAID-6 scheme)
  vertical    V[c] = XOR of that channel's 4 bits       (checked when the block ends)

A cell the receiver knows is dead (invalid Manchester symbol) is an unknown.
Decoding is "peeling": any equation with exactly one unknown gives that bit.

Run: python3 docs/experiments/matrix_code.py
"""
import itertools

CH = ("D0", "D1", "P", "Q")
ROWS, TICKS = 4, 5  # 4 data ticks + 1 vertical-check tick


def equations():
    """Each equation is a list of (tick, channel) cells whose XOR must be 0."""
    eqs = []
    for i in range(ROWS + 1):  # horizontal also holds on the vertical tick
        eqs.append(("H%d" % i, [(i, 0), (i, 1), (i, 2)]))
    diag = [[(0, 0), (1, 2)], [(1, 0), (0, 1), (2, 2)], [(2, 0), (1, 1), (3, 2)], [(3, 0), (2, 1)]]
    for d, cells in enumerate(diag):
        eqs.append(("Q%d" % d, cells + [(d, 3)]))
    for c in range(4):
        eqs.append(("V%s" % CH[c], [(i, c) for i in range(TICKS)]))
    return eqs


EQS = equations()


def encode(byte):
    """byte -> 5x4 matrix. D0 takes the even bits (MSB first), D1 the odd ones."""
    bits = [(byte >> (7 - n)) & 1 for n in range(8)]
    m = [[0] * 4 for _ in range(TICKS)]
    for i in range(ROWS):
        m[i][0], m[i][1] = bits[2 * i], bits[2 * i + 1]
        m[i][2] = m[i][0] ^ m[i][1]
    m[0][3] = m[0][0] ^ m[1][2]
    m[1][3] = m[1][0] ^ m[0][1] ^ m[2][2]
    m[2][3] = m[2][0] ^ m[1][1] ^ m[3][2]
    m[3][3] = m[3][0] ^ m[2][1]
    for c in range(4):
        m[4][c] = m[0][c] ^ m[1][c] ^ m[2][c] ^ m[3][c]
    return m


def to_byte(m):
    v = 0
    for i in range(ROWS):
        v = (v << 2) | (m[i][0] << 1) | m[i][1]
    return v


def failing(m):
    """Names of the equations that do not come out even (None cells make an equation undecided)."""
    out = []
    for name, cells in EQS:
        vals = [m[i][c] for i, c in cells]
        if None not in vals and sum(vals) % 2:
            out.append(name)
    return out


def peel(m):
    """Fill unknown cells (None) using equations with exactly one unknown. -> cells still unknown"""
    m = [row[:] for row in m]
    progress = True
    while progress:
        progress = False
        for _, cells in EQS:
            unknown = [(i, c) for i, c in cells if m[i][c] is None]
            if len(unknown) == 1:
                i, c = unknown[0]
                m[i][c] = sum(m[a][b] for a, b in cells if (a, b) != (i, c)) % 2
                progress = True
    return m, sum(v is None for row in m for v in row)


CODEWORDS = [encode(b) for b in range(256)]


def decode(m):
    """-> (byte or None, outcome). Unknown cells are None; known cells may still be lying."""
    solved, left = peel(m)
    if left == 0 and not failing(solved):
        return to_byte(solved), "ok" if solved == m else "rebuilt"
    # something lies: find the codeword that explains it best
    known = [(i, c) for i in range(TICKS) for c in range(4) if m[i][c] is not None]
    # (a) a single lying bit
    hits = [w for w in CODEWORDS if sum(w[i][c] != m[i][c] for i, c in known) == 1]
    if len(hits) == 1:
        return to_byte(hits[0]), "fixed bit"
    # (b) one whole channel lying: every equation that avoids it must hold
    hits = set()
    for bad in range(4):
        for w in CODEWORDS:
            if all(w[i][c] == m[i][c] for i, c in known if c != bad):
                hits.add(to_byte(w))
    if len(hits) == 1:
        return hits.pop(), "fixed channel"
    return None, "detected"


def kill(m, chans, ticks=range(TICKS)):
    return [[None if (c in chans and i in ticks) else v for c, v in enumerate(row)] for i, row in enumerate(m)]


def check():
    res = {}
    # 1. any 2 channels dead for the whole block
    bad = 0
    for b in range(256):
        for pair in itertools.combinations(range(4), 2):
            bad += decode(kill(CODEWORDS[b], pair)) != (b, "rebuilt")
    res["2 channels dead all block: failures"] = "%d of %d" % (bad, 256 * 6)
    # 2. any 3 channels dead
    ok = sum(decode(kill(CODEWORDS[b], t))[0] == b for b in range(256) for t in itertools.combinations(range(4), 3))
    res["3 channels dead: recovered"] = "%d of %d" % (ok, 256 * 4)
    # 3. one lying bit, nothing dead
    bad = 0
    for b in range(0, 256, 5):
        for i in range(TICKS):
            for c in range(4):
                m = [r[:] for r in CODEWORDS[b]]
                m[i][c] ^= 1
                bad += decode(m)[0] != b
    res["1 lying bit: failures"] = bad
    # 4. one channel lying arbitrarily (not flagged as dead), nothing else wrong
    bad = wrong = n = 0
    for b in range(0, 256, 7):
        for c in range(4):
            for pat in range(1, 32):
                m = [r[:] for r in CODEWORDS[b]]
                for i in range(TICKS):
                    m[i][c] ^= (pat >> i) & 1
                got = decode(m)[0]
                n += 1
                bad += got != b
                wrong += got is not None and got != b
    res["1 channel lying any way: not recovered"] = "%d of %d (wrong data accepted: %d)" % (bad, n, wrong)
    # 5. one channel dead + one lying bit elsewhere
    bad = wrong = n = 0
    for b in range(0, 256, 5):
        for dead in range(4):
            for i in range(TICKS):
                for c in range(4):
                    if c == dead:
                        continue
                    m = kill(CODEWORDS[b], (dead,))
                    m[i][c] ^= 1
                    got = decode(m)[0]
                    n += 1
                    bad += got != b
                    wrong += got is not None and got != b
    res["1 dead + 1 lying bit: not recovered"] = "%d of %d (wrong data accepted: %d)" % (bad, n, wrong)
    # 6. two channels dead + one lying bit in a survivor
    wrong = n = 0
    for b in range(0, 256, 5):
        for pair in itertools.combinations(range(4), 2):
            for i in range(TICKS):
                for c in range(4):
                    if c in pair:
                        continue
                    m = kill(CODEWORDS[b], pair)
                    m[i][c] ^= 1
                    got = decode(m)[0]
                    n += 1
                    wrong += got is not None and got != b
    res["2 dead + 1 lying bit: wrong data accepted"] = "%d of %d" % (wrong, n)
    # 7. minimum distance
    flat = lambda m: [v for r in m for v in r]
    res["minimum distance"] = min(sum(flat(w)) for w in CODEWORDS[1:])
    return res


def show(m):
    print("          D0  D1  P   Q")
    for i, row in enumerate(m):
        print("  tick %d   %s" % (i, "   ".join("E" if v is None else str(v) for v in row))
              + ("   <- vertical check" if i == ROWS else ""))


if __name__ == "__main__":
    print("'h' = 0x68 = 01101000")
    h = encode(0x68)
    show(h)
    print("\nhand on D0 and D1 for the whole block:")
    m = kill(h, (0, 1))
    show(m)
    print("decoded:", "0x%02X %s" % decode(m))
    print("\none bit flipped (tick 2, D1): equations that fail ->", end=" ")
    m = [r[:] for r in h]
    m[2][1] ^= 1
    print(failing(m), "-> decoded 0x%02X %s" % decode(m))
    print()
    for k, v in check().items():
        print("%-45s %s" % (k, v))
