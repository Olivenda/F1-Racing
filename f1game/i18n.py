# Copyright Olivenda (Oliver Petz) 2026

from __future__ import annotations

import re
from typing import Callable

from .i18n_en import EXACT, PATTERNS

LANG = "en"
LANGUAGES = {"en": "English", "de": "Deutsch"}

_exact = {k.lower(): v for k, v in EXACT.items()}
_patterns: list[tuple[re.Pattern[str], str | Callable[[re.Match[str]], str]]] = [
    (re.compile(p, re.IGNORECASE | re.DOTALL), r) for p, r in PATTERNS]
_cache: dict[str, str] = {}
MISSES: set[str] = set()
RECORD_MISSES = False


def set_language(lang: str) -> None:
    global LANG
    LANG = lang if lang in LANGUAGES else "en"
    _cache.clear()


def _match_case(src: str, out: str) -> str:
    letters = [c for c in src if c.isalpha()]
    if letters and all(c.isupper() for c in letters) and len(letters) > 1:
        return out.upper()
    return out


def _translate(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return text
    hit = _exact.get(stripped.lower())
    if hit is not None:
        return text.replace(stripped, _match_case(stripped, hit))
    for pattern, repl in _patterns:
        m = pattern.fullmatch(stripped)
        if m:
            if callable(repl):
                out = repl(m)
            else:
                out = m.expand(repl)
                out = re.sub(r"\[\[(.*?)\]\]", lambda g: tr(g.group(1)), out)
            return text.replace(stripped, _match_case(stripped, out))
    if RECORD_MISSES:
        MISSES.add(stripped)
    return text


def tr(text: str) -> str:
    if LANG == "de" or not text:
        return text
    out = _cache.get(text)
    if out is None:
        out = _translate(text)
        if len(_cache) > 6000:
            _cache.clear()
        _cache[text] = out
    return out
