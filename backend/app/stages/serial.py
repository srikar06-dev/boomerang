"""Serial comparison that tolerates OCR, the way real systems treat it: never character-exact.

- Look-alike characters are folded together (O/0, I/L/1, S/5, B/8, Z/2), on both sides.
- The model lists EVERY code printed on the label (serial, model number, FNSKU, ...); the shipped
  serial only has to be one of them. Labels carry several codes and the model may pick the wrong line.
- One wrong character on a serial of 6+ characters still counts as a match (a single misread).
The model is never told the expected serial (it would echo it back); only this code compares.
"""
import re

FOLD = str.maketrans({"O": "0", "Q": "0", "D": "0", "I": "1", "L": "1", "S": "5", "B": "8", "Z": "2", "G": "6"})
FUZZY_MIN_LEN = 6


def norm(text: str | None) -> str | None:
    """Uppercase letters and digits only, look-alikes folded: 'sn-O57 bna' -> '5N057' + ..."""
    cleaned = re.sub(r"[^A-Z0-9]", "", (text or "").upper())
    return cleaned.translate(FOLD) or None


def _within_one_edit(a: str, b: str) -> bool:
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    short, long_ = (a, b) if len(a) < len(b) else (b, a)
    return any(long_[:i] + long_[i + 1:] == short for i in range(len(long_)))


def matches(expected: str | None, reads: list[str | None]) -> bool | None:
    """True = the shipped serial is on the label, False = codes were read but none match,
    None = nothing readable (or nothing expected): no serial evidence either way."""
    want = norm(expected)
    got = [r for r in (norm(x) for x in reads) if r]
    if not want or not got:
        return None
    for r in got:
        if r == want or (len(want) >= FUZZY_MIN_LEN and _within_one_edit(r, want)):
            return True
        if len(r) > len(want) and want in r:          # serial printed inside a longer code/barcode text
            return True
    return False
