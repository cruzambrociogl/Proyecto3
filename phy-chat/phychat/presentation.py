"""Presentation layer: text <-> 8-bit units.

UTF-8 is implemented by hand (1 to 4 bytes per code point) so the encoding
rules are visible; Extended ASCII uses single-byte code pages. The id of the
selected encoding travels in the START frame so the receiver decodes with
the same scheme the sender used.
"""

REPLACEMENT = "�"

ENCODINGS = {
    0: ("utf-8", "Unicode UTF-8"),
    1: ("cp437", "Extended ASCII (CP437)"),
    2: ("latin-1", "Extended ASCII (ISO-8859-1)"),
}
ENCODING_IDS = {name: i for i, (name, _) in ENCODINGS.items()}

_UTF8_MIN = {2: 0x80, 3: 0x800, 4: 0x10000}  # smallest code point per length (rejects overlong forms)


def utf8_encode_char(ch):
    cp = ord(ch)
    if cp < 0x80:
        return bytes([cp])
    if cp < 0x800:
        return bytes([0xC0 | (cp >> 6), 0x80 | (cp & 0x3F)])
    if 0xD800 <= cp <= 0xDFFF:
        return utf8_encode_char(REPLACEMENT)  # lone surrogates are not encodable
    if cp < 0x10000:
        return bytes([0xE0 | (cp >> 12), 0x80 | ((cp >> 6) & 0x3F), 0x80 | (cp & 0x3F)])
    return bytes([0xF0 | (cp >> 18), 0x80 | ((cp >> 12) & 0x3F),
                  0x80 | ((cp >> 6) & 0x3F), 0x80 | (cp & 0x3F)])


class Utf8Decoder:
    """Streaming decoder: bytes arrive one frame at a time."""

    def __init__(self):
        self.need = 0
        self.length = 0
        self.cp = 0

    def feed(self, b):
        out = ""
        if self.need:
            if b & 0xC0 == 0x80:
                self.cp = (self.cp << 6) | (b & 0x3F)
                self.need -= 1
                if self.need:
                    return ""
                cp = self.cp
                if cp < _UTF8_MIN[self.length] or 0xD800 <= cp <= 0xDFFF or cp > 0x10FFFF:
                    return REPLACEMENT
                return chr(cp)
            out = REPLACEMENT  # sequence cut short by a new lead byte
            self.need = 0
        if b < 0x80:
            return out + chr(b)
        if 0xC2 <= b <= 0xDF:
            self.length, self.cp = 2, b & 0x1F
        elif 0xE0 <= b <= 0xEF:
            self.length, self.cp = 3, b & 0x0F
        elif 0xF0 <= b <= 0xF4:
            self.length, self.cp = 4, b & 0x07
        else:
            return out + REPLACEMENT  # continuation without lead, or C0/C1/F5..FF
        self.need = self.length - 1
        return out

    def flush(self):
        if self.need:
            self.need = 0
            return REPLACEMENT
        return ""


class SingleByteDecoder:
    def __init__(self, codec):
        self.codec = codec

    def feed(self, b):
        return bytes([b]).decode(self.codec)

    def flush(self):
        return ""


def encode_chars(text, enc_id):
    """Returns [(char, bytes)] so the log can show how each character was encoded."""
    name = ENCODINGS[enc_id][0]
    if name == "utf-8":
        return [(ch, utf8_encode_char(ch)) for ch in text]
    return [(ch, ch.encode(name, errors="replace")) for ch in text]


def decoder(enc_id):
    name = ENCODINGS[enc_id][0]
    return Utf8Decoder() if name == "utf-8" else SingleByteDecoder(name)
