"""Plate normalisation — where OCR mess becomes evidence-grade text.

The raw OCR output is treated as untrusted. Normalisation is two stages:

1. **Lossless** strip: uppercase, drop separators/whitespace. The result is the
   ``normalized`` string and is always safe to store.
2. **Positional de-confusion** for the Indian ``LL NN LL NNNN`` layout: an
   OCR engine routinely confuses ``G``/``6``, ``O``/``0``, ``I``/``1``, ``B``/``8``.
   Because the layout tells us which slots are letters and which are digits, we
   can *justify* a correction (``6`` in a letter slot is almost certainly ``G``)
   rather than guess. Every substitution is recorded in ``corrections``.

Nothing is ever silently invented: a character that is of the wrong type and is
not a known confusion leaves ``valid=False`` so the event is down-ranked rather
than "fixed" into a fake plate. This was validated against the real OCR engine,
which returned ``6J01AB1234`` for a ``GJ01AB1234`` plate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#: Slots (0-based) in a 10-char Indian plate that must be letters / digits.
LETTER_SLOTS = frozenset({0, 1, 4, 5})
DIGIT_SLOTS = frozenset({2, 3, 6, 7, 8, 9})

#: Digit-as-letter corrections (used in letter slots).
DIGIT_TO_LETTER = {"0": "O", "1": "I", "2": "Z", "5": "S", "6": "G", "8": "B"}
#: Letter-as-digit corrections (used in digit slots).
LETTER_TO_DIGIT = {"O": "0", "I": "1", "Z": "2", "S": "5", "G": "6", "B": "8", "D": "0", "Q": "0"}

#: Plausible Indian state/RTO codes for the first two letter slots. Not
#: exhaustive — a plate whose code is absent here is still *stored*, just not
#: used for high-confidence watchlist matching.
KNOWN_STATE_CODES = {
    "GJ", "MH", "RJ", "DL", "HR", "UP", "MP", "CG", "PB", "KA", "TN", "AP", "TS",
    "KL", "WB", "OD", "BR", "JH", "AS", "GA", "HP", "UK", "JK", "CH", "PY", "TR",
    "MN", "ML", "NL", "SK", "AR", "MZ", "LD", "DN", "AN",
}

_INDIAN_PATTERN = re.compile(r"^[A-Z]{2}\d{2}[A-Z]{2}\d{4}$")
_STRIP_PATTERN = re.compile(r"[^A-Z0-9]")


@dataclass
class NormalizedPlate:
    raw: str
    normalized: str = ""
    corrections: list[tuple[int, str, str]] = field(default_factory=list)
    valid: bool = False
    length_ok: bool = False
    state_code_known: bool = False
    pattern: str = "indian"

    @property
    def is_indian(self) -> bool:
        return bool(_INDIAN_PATTERN.match(self.normalized))

    def describe(self) -> dict:
        return {
            "raw": self.raw,
            "normalized": self.normalized,
            "valid": self.valid,
            "corrections": [list(c) for c in self.corrections],
            "state_code_known": self.state_code_known,
        }


def strip_to_alnum(raw: str) -> str:
    """Stage 1: uppercase and drop everything that is not A-Z or 0-9."""
    return _STRIP_PATTERN.sub("", (raw or "").upper())


def normalize_plate(
    raw: str, min_len: int = 8, max_len: int = 13
) -> NormalizedPlate:
    """Full normalisation. See module docstring for the trust model."""
    result = NormalizedPlate(raw=raw or "")
    stripped = strip_to_alnum(raw)
    result.normalized = stripped
    result.length_ok = min_len <= len(stripped) <= max_len
    if not result.length_ok:
        return result

    corrected = list(stripped)
    if len(stripped) == 10:
        for index, char in enumerate(stripped):
            if index in LETTER_SLOTS and char.isdigit():
                mapped = DIGIT_TO_LETTER.get(char)
                if mapped:
                    result.corrections.append((index, char, mapped))
                    corrected[index] = mapped
            elif index in DIGIT_SLOTS and char.isalpha():
                mapped = LETTER_TO_DIGIT.get(char)
                if mapped:
                    result.corrections.append((index, char, mapped))
                    corrected[index] = mapped
        candidate = "".join(corrected)
        # Only adopt the corrected string if it satisfies the Indian layout.
        if _INDIAN_PATTERN.match(candidate):
            result.normalized = candidate
    result.valid = _INDIAN_PATTERN.match(result.normalized) is not None
    result.state_code_known = result.normalized[:2] in KNOWN_STATE_CODES if result.valid else False
    return result


def is_plausible_indian_plate(text: str) -> bool:
    return _INDIAN_PATTERN.match(strip_to_alnum(text)) is not None


def plate_score(plate: NormalizedPlate) -> float:
    """0..1 prior on how trustworthy a normalised plate is, before OCR conf.

    Used to rank candidates and to gate high-confidence alerting.
    """
    score = 0.0
    if plate.valid:
        score += 0.6
    if plate.state_code_known:
        score += 0.2
    if plate.length_ok:
        score += 0.2
    if plate.corrections:
        # A correction is evidence we *had* to guess: keep it honest.
        score -= 0.05 * min(len(plate.corrections), 3)
    return round(max(0.0, min(1.0, score)), 3)
