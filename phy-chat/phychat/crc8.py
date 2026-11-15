"""CRC-8 variants (parameters from the RevEng CRC catalogue).

All four run through the same bitwise engine; a variant is just its
polynomial, initial value, reflection flags and final XOR.
"""


def _reflect8(x):
    r = 0
    for i in range(8):
        if x & (1 << i):
            r |= 1 << (7 - i)
    return r


class Crc8:
    def __init__(self, name, poly, init, refin, refout, xorout, check):
        self.name = name
        self.poly = poly
        self.init = init
        self.refin = refin
        self.refout = refout
        self.xorout = xorout
        self.check = check  # expected CRC of b"123456789"

    def compute(self, data):
        crc = self.init
        for b in data:
            if self.refin:
                b = _reflect8(b)
            crc ^= b
            for _ in range(8):
                if crc & 0x80:
                    crc = ((crc << 1) ^ self.poly) & 0xFF
                else:
                    crc = (crc << 1) & 0xFF
        if self.refout:
            crc = _reflect8(crc)
        return crc ^ self.xorout

    def describe(self):
        return {
            "name": self.name, "poly": "0x%02X" % self.poly, "init": "0x%02X" % self.init,
            "refin": self.refin, "refout": self.refout, "xorout": "0x%02X" % self.xorout,
        }


VARIANTS = {
    "SMBUS": Crc8("SMBUS", 0x07, 0x00, False, False, 0x00, 0xF4),
    "AUTOSAR": Crc8("AUTOSAR", 0x2F, 0xFF, False, False, 0xFF, 0xDF),
    "SAE-J1850": Crc8("SAE-J1850", 0x1D, 0xFF, False, False, 0xFF, 0x4B),
    "MAXIM-DOW": Crc8("MAXIM-DOW", 0x31, 0x00, True, True, 0x00, 0xA1),
}
VARIANT_IDS = {name: i for i, name in enumerate(VARIANTS)}  # 2-bit id announced in PING/PONG

# PING/PONG always use this one, so two nodes with different settings can still
# read each other's announcement
MGMT = VARIANTS["SMBUS"]
