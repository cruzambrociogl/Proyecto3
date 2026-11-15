"""v6b against the professor's "fast flicker" and against the same noise on every channel.

Flicker model: on a flickered channel every tick is 4 random reads. Only 0011
and 1100 are valid symbols, so a tick is dead (E) 14 times out of 16 and a
random valid bit (a lie) 2 times out of 16.

Compares three receivers:
  plain    matrix_nibble.decode as it is: every valid-looking cell is believed
  trust    channels with no dead tick in this matrix are asked first; a channel
           that showed any dead tick is only used if the clean ones are not enough
  strict   three kinds of reading: valid, blocked (0000 hand / 1111 IR), noisy
           (any other pattern). A channel that showed noise in this matrix is
           never believed; a channel that was only blocked keeps its good ticks

Also checks the "inverted channels" mask: D1 and Q are sent inverted, so the
same reading on all four channels can never be a valid matrix.

Run: python3 docs/experiments/flicker_nibble.py
"""
import itertools
import random

from matrix_nibble import CODEWORDS, TICKS, decode, kill

TRIALS = 20000


def flicker(m, chans, rng):
    """-> (matrix, channels that showed a noisy pattern)"""
    m = [r[:] for r in m]
    noisy = set()
    for c in chans:
        for t in range(TICKS):
            reads = rng.getrandbits(4)
            m[t][c] = 1 if reads == 0b0011 else 0 if reads == 0b1100 else None
            if reads not in (0b0011, 0b1100, 0b0000, 0b1111):
                noisy.add(c)
    return m, noisy


def decode_plain(m, noisy):
    return decode(m)


def decode_strict(m, noisy):
    return decode(kill(m, noisy))


def decode_trust(m, noisy):
    suspect = [c for c in range(4) if any(m[t][c] is None for t in range(TICKS))]
    if suspect and len(suspect) < 4:
        got = decode(kill(m, suspect))
        if got[0] is not None:
            return got
    return decode(m)


def run(dec, flickered, dead, rng):
    good = again = wrong = 0
    for _ in range(TRIALS):
        n = rng.randrange(16)
        chans = rng.sample(range(4), flickered + dead)
        m, noisy = flicker(kill(CODEWORDS[n], chans[:dead]), chans[dead:], rng)
        got = dec(m, noisy)[0]
        good += got == n
        again += got is None
        wrong += got is not None and got != n
    return "recovered %5.1f%%  asked again %5.1f%%  WRONG %5.2f%%" % (
        100 * good / TRIALS, 100 * again / TRIALS, 100 * wrong / TRIALS)


def common_mode(mask):
    """How many 'same 5 bits on all channels' readings pass as a valid matrix, and how close they get."""
    valid, nearest = 0, 99
    for x in itertools.product((0, 1), repeat=TICKS):
        d = min(sum((w[t][c] ^ mask[c]) != x[t] for t in range(TICKS) for c in range(4)) for w in CODEWORDS)
        valid += d == 0
        nearest = min(nearest, d)
    return "valid matrices: %d of 32, closest is %d cells away" % (valid, nearest)


if __name__ == "__main__":
    for flickered, dead in ((1, 0), (2, 0), (3, 0), (4, 0), (1, 2), (2, 1), (1, 3)):
        print("%d flickering, %d dead, %d clean" % (flickered, dead, 4 - flickered - dead))
        for name, dec in (("plain", decode_plain), ("trust", decode_trust), ("strict", decode_strict)):
            print("   %-6s %s" % (name, run(dec, flickered, dead, random.Random(7))))
    print("\nsame reading on all 4 channels (noise that hits every sensor alike):")
    print("   no mask               ", common_mode((0, 0, 0, 0)))
    print("   D1 and Q inverted     ", common_mode((0, 1, 0, 1)))
    print("   D1 inverted           ", common_mode((0, 1, 0, 0)))
