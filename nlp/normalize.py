"""Deterministic multilingual text normalization for ``ru`` / ``kk`` / ``en`` (Phase 10).

Implements TZ §11.2:
  - Unicode NFC canonicalization;
  - Zero-width and control character stripping;
  - Casefolding + punctuation/quote normalization;
  - Legal-entity form canonicalization across English, Russian, and Kazakh
    (``ТОО`` / ``ЖШС`` / ``LLP`` / ``АО`` / ``АҚ`` / ``ООО`` / ``GmbH``);
  - Deterministic Cyrillic + Kazakh Cyrillic -> ASCII phonetic skeleton for
    cross-script candidate entity linking (STRICTLY hypothesis-tier).

Pure stdlib only — zero external NLP dependencies.
"""

from __future__ import annotations

import re
import unicodedata

# Zero-width & bidi control code points stripped before tokenization
_ZERO_WIDTH_RE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060\ufeff]")
_QUOTES_RE = re.compile(r"""["'«»„“”‘’`]+""")
_PUNCT_WS_RE = re.compile(r"[^\w\s:#/-]+", re.UNICODE)
_MULTI_WS_RE = re.compile(r"\s+")

# Legal entity forms mapped to canonical tags across ru/kk/en
LEGAL_FORM_SYNONYMS: dict[str, str] = {
    "тоо": "llp",
    "жшс": "llp",
    "llp": "llp",
    "llc": "llp",
    "ооо": "llp",
    "gmbh": "llp",
    "ltd": "ltd",
    "corp": "corp",
    "ао": "jsc",
    "ақ": "jsc",
    "ак": "jsc",
    "jsc": "jsc",
    "ип": "sole_prop",
    "жк": "sole_prop",
}

_LONG_LEGAL_PHRASES: tuple[tuple[str, str], ...] = (
    ("товарищество с ограниченной ответственностью", "llp"),
    ("жауапкершілігі шектеулі серіктестік", "llp"),
    ("акционерное общество", "jsc"),
    ("акционерлік қоғам", "jsc"),
    ("limited liability partnership", "llp"),
)

# Deterministic Kazakh + Russian Cyrillic -> ASCII phonetic transliteration table
_CYR_TO_LATIN: dict[str, str] = {
    "а": "a",
    "ә": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "ғ": "g",
    "д": "d",
    "е": "e",
    "ё": "yo",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "і": "i",
    "к": "k",
    "қ": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "ң": "ng",
    "о": "o",
    "ө": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ұ": "u",
    "ү": "u",
    "ф": "f",
    "х": "kh",
    "һ": "h",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "shch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
}


def normalize_nfc(text: str) -> str:
    """Return NFC-normalized string with zero-width characters removed."""
    if not isinstance(text, str):
        raise TypeError("text must be a str")
    cleaned = _ZERO_WIDTH_RE.sub("", unicodedata.normalize("NFC", text))
    return cleaned


def normalize_accounting_text(text: str, *, canonicalize_legal_forms: bool = True) -> str:
    """Normalize multilingual accounting prose into a deterministic lowercase string."""
    s = normalize_nfc(text).casefold()
    s = _QUOTES_RE.sub(" ", s)
    if canonicalize_legal_forms:
        for phrase, canon in _LONG_LEGAL_PHRASES:
            if phrase in s:
                s = s.replace(phrase, f" {canon} ")
    s = _PUNCT_WS_RE.sub(" ", s)
    tokens = [t for t in _MULTI_WS_RE.split(s.strip()) if t]
    if canonicalize_legal_forms:
        tokens = [LEGAL_FORM_SYNONYMS.get(tok.rstrip("."), tok) for tok in tokens]
    return " ".join(tokens)


def transliterate_to_ascii_skeleton(text: str) -> str:
    """Project Cyrillic/Kazakh/Latin entity text onto a shared ASCII skeleton."""
    norm = normalize_accounting_text(text, canonicalize_legal_forms=True)
    out: list[str] = []
    for ch in norm:
        if ch in _CYR_TO_LATIN:
            out.append(_CYR_TO_LATIN[ch])
        elif ch.isascii():
            out.append(ch)
        else:
            # Strip diacritics on extended Latin (e.g. ä -> a)
            decomp = unicodedata.normalize("NFKD", ch)
            out.extend(c for c in decomp if c.isascii() and not unicodedata.combining(c))
    return _MULTI_WS_RE.sub(" ", "".join(out)).strip()


def char_ngrams(text: str, n: int = 3) -> frozenset[str]:
    """Extract deterministic padded character n-grams for candidate similarity."""
    if n < 1:
        raise ValueError("n must be >= 1")
    norm = normalize_accounting_text(text, canonicalize_legal_forms=True)
    if not norm:
        return frozenset()
    padded = f"$${norm}$$"
    if len(padded) < n:
        return frozenset({padded})
    return frozenset(padded[i : i + n] for i in range(len(padded) - n + 1))


__all__ = [
    "LEGAL_FORM_SYNONYMS",
    "char_ngrams",
    "normalize_accounting_text",
    "normalize_nfc",
    "transliterate_to_ascii_skeleton",
]
