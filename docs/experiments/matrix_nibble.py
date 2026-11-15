"""v6b: one NIBBLE = one matrix, so that ONE surviving channel is enough.

Same 5x4 picture as v6 (matrix_code.py), but every channel carries the whole
nibble (a b c d) in a different XOR form, plus its own vertical check:

            D0     D1     P        Q
  tick 0    a      b      a^b      a^b^c
  tick 1    b      c      b^c      b^c^d
  tick 2    c      d      c^d      a^b^c^d
  tick 3    d      a^b    a^b^d    a^c^d
  tick 4    V      V      V        V        V = XOR of the 4 cells above it

  horizontal  P[t] = D0[t] ^ D1[t]             every tick, tick 4 included
  diagonal    D1[t] = D0[t+1]                  t = 0..2
              Q[t]  = D0[t] ^ P[t+1]           t = 0..2
  vertical    V[c]  = XOR of that channel's 4 cells

Every cell is one XOR equation in a, b, c, d. The receiver keeps the cells that
arrived and solves for a, b, c, d (here: tries the 16 nibbles, same result).

The columns are windows of one sequence s[k+4] = s[k] ^ s[k+1] that starts
a, b, c, d: D0 starts at 0, D1 at 1, P at 4, Q at 10.

Run: python3 docs/experiments/matrix_nibble.py
"""
import itertools

CH = ("D0", "D1", "P", "Q")
OFFSET = (0, 1, 4, 10)
TICKS = 5

SEQ = [8, 4, 2, 1]  # masks over the nibble bits a b c d (a = MSB)
while len(SEQ) < 15:
    SEQ.append(SEQ[-4] ^ SEQ[-3])


def recipe(c):
    """Masks of the 5 cells of channel c: 4 window cells + their XOR."""
    cells = [SEQ[(OFFSET[c] + t) % 15] for t in range(4)]
    return cells + [cells[0] ^ cells[1] ^ cells[2] ^ cells[3]]


RECIPE = [recipe(c) for c in range(4)]


def encode(nib):
    """nibble -> matrix m[tick][channel]"""
    return [[bin(nib & RECIPE[c][t]).count("1") & 1 for c in range(4)] for t in range(TICKS)]


CODEWORDS = [encode(n) for n in range(16)]
CELLS = [(t, c) for t in range(TICKS) for c in range(4)]


def decode(m):
    """-> (nibble or None, outcome). Dead cells are None; known cells may still lie."""
    known = [(t, c) for t, c in CELLS if m[t][c] is not None]
    dist = [sum(w[t][c] != m[t][c] for t, c in known) for w in CODEWORDS]
    fits = [n for n in range(16) if dist[n] == 0]
    if len(fits) == 1:
        return fits[0], "ok" if len(known) == len(CELLS) else "rebuilt"
    if len(fits) > 1:
        return None, "lost"  # not enough cells arrived
    # something lies. (a) few lying bits: nearest matrix, only inside the safe radius
    gap = min(sum(CODEWORDS[n][t][c] for t, c in known) for n in range(1, 16))
    best = min(dist)
    if 2 * best < gap and dist.count(best) == 1:
        return dist.index(best), "fixed bits"
    # (b) one whole channel lies: drop each channel in turn, see what the rest says
    hits = set()
    for bad in range(4):
        rest = [(t, c) for t, c in known if c != bad]
        if not rest:
            continue
        ok = [n for n in range(16) if all(CODEWORDS[n][t][c] == m[t][c] for t, c in rest)]
        if len(ok) == 1:
            hits.add(ok[0])
    if len(hits) == 1:
        return hits.pop(), "fixed channel"
    return None, "detected"


def kill(m, chans=(), ticks=range(TICKS)):
    return [[None if (c in chans and t in ticks) else v for c, v in enumerate(row)] for t, row in enumerate(m)]


def lie(m, c, pat):
    m = [r[:] for r in m]
    for t in range(TICKS):
        if m[t][c] is not None:
            m[t][c] ^= (pat >> t) & 1
    return m


def tally(cases):
    """cases: iterable of (sent nibble, received matrix) -> 'fixed / detected / wrong'"""
    good = det = wrong = 0
    for n, m in cases:
        got = decode(m)[0]
        good += got == n
        det += got is None
        wrong += got is not None and got != n
    return "recovered %d, asked again %d, WRONG accepted %d (of %d)" % (good, det, wrong, good + det + wrong)


def check():
    res = {}
    comb = itertools.combinations
    N = range(16)
    for k in (1, 2, 3, 4):
        res["%d channels dead all block" % k] = tally(
            (n, kill(CODEWORDS[n], d)) for n in N for d in comb(range(4), k))
    for lost in (1, 2):
        res["1 channel alive, it loses %d tick(s)" % lost] = tally(
            (n, kill(kill(CODEWORDS[n], [c for c in range(4) if c != alive]), (alive,), ticks))
            for n in N for alive in range(4) for ticks in comb(range(TICKS), lost))
    for lost in (1, 2):
        res["2 channels alive, each loses %d tick(s)" % lost] = tally(
            (n, kill(kill(kill(CODEWORDS[n], [c for c in range(4) if c not in pair]), (pair[0],), t0), (pair[1],), t1))
            for n in N for pair in comb(range(4), 2)
            for t0 in comb(range(TICKS), lost) for t1 in comb(range(TICKS), lost))
    for dark in (1, 2, 3):
        res["blackout: ALL channels dark %d tick(s) in a row" % dark] = tally(
            (n, kill(CODEWORDS[n], range(4), range(s, s + dark))) for n in N for s in range(TICKS - dark + 1))
    for flips in (1, 2, 3):
        res["%d lying bit(s), nothing dead" % flips] = tally(
            (n, [[v ^ ((t, c) in f) for c, v in enumerate(row)] for t, row in enumerate(CODEWORDS[n])])
            for n in N for f in comb(CELLS, flips))
    P = range(1, 32)
    res["1 channel lying any way"] = tally(
        (n, lie(CODEWORDS[n], c, p)) for n in N for c in range(4) for p in P)
    res["1 dead + 1 channel lying any way"] = tally(
        (n, lie(kill(CODEWORDS[n], (d,)), c, p)) for n in N for d in range(4) for c in range(4) if c != d for p in P)
    res["2 dead + 1 channel lying any way"] = tally(
        (n, lie(kill(CODEWORDS[n], d), c, p)) for n in N for d in comb(range(4), 2)
        for c in range(4) if c not in d for p in P)
    res["3 dead + the last one lying any way"] = tally(
        (n, lie(kill(CODEWORDS[n], [x for x in range(4) if x != c]), c, p)) for n in N for c in range(4) for p in P)
    res["2 channels lying any way, nothing dead"] = tally(
        (n, lie(lie(CODEWORDS[n], c0, p0), c1, p1)) for n in N for c0, c1 in comb(range(4), 2) for p0 in P for p1 in P)
    res["minimum distance"] = min(sum(map(sum, w)) for w in CODEWORDS[1:])
    return res


def show(m):
    print("          D0  D1  P   Q")
    for t, row in enumerate(m):
        print("  tick %d   %s" % (t, "   ".join("E" if v is None else str(v) for v in row))
              + ("   <- vertical check" if t == TICKS - 1 else ""))


if __name__ == "__main__":
    names = "abcd"
    print("recipes (which nibble bits are XORed in each cell):")
    for t in range(TICKS):
        print("  tick %d   " % t + "  ".join(
            "%-8s" % "^".join(names[i] for i in range(4) if RECIPE[c][t] & (8 >> i)) for c in range(4)))
    for nib in (0x6, 0x8):
        print("\nnibble %X = %s" % (nib, format(nib, "04b")))
        show(encode(nib))
    print("\nnibble 6 with D0, D1 and P dead (only Q alive):")
    m = kill(encode(0x6), (0, 1, 2))
    show(m)
    print("decoded: %X %s" % decode(m))
    print()
    for k, v in check().items():
        print("%-46s %s" % (k, v))
