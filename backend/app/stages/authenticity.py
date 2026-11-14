"""Authenticity: has this exact picture (or a near copy) been used before?"""
import imagehash

PHASH_MAX_DISTANCE = 6   # out of 64 bits; re-saved or lightly cropped copies land under this


def is_reused(sha256: str, phash: str, known_sha256: set[str], known_phash: list[str]) -> bool:
    """True if the upload matches any earlier photo: byte-identical, or visually the same."""
    if sha256 in known_sha256:
        return True
    mine = imagehash.hex_to_hash(phash)
    for other in known_phash:
        try:
            if mine - imagehash.hex_to_hash(other) <= PHASH_MAX_DISTANCE:
                return True
        except (ValueError, TypeError):
            continue
    return False
