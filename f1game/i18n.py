# Copyright Olivenda (Oliver Petz) 2026

from __future__ import annotations

import re
from typing import Callable

from .i18n_en import EXACT, PATTERNS, TEMPLATES

LANG = "en"
LANGUAGES = {"en": "English", "de": "Deutsch"}


def compile_template(de: str, en: str) -> tuple[str, str]:
    """Turn 'Saison {} · Ruf {#}' / 'Season {} · rep {#}' into a regex and an expand() template.
    {} captures text that is translated again, {#} captures a number, {2} in the English text reorders."""
    regex, kinds = "", []
    for part in re.split(r"(\{\}|\{#\})", de):
        if part == "{}":
            regex += "(.+?)"
            kinds.append("t")
        elif part == "{#}":
            regex += r"([-+]?\d[\d.,:]*)"
            kinds.append("n")
        else:
            regex += re.escape(part)
    counter = 0

    def group(m: re.Match[str]) -> str:
        nonlocal counter
        if m.group(1):
            idx = int(m.group(1))
        else:
            counter += 1
            idx = counter
        ref = f"\\g<{idx}>"
        return ref if kinds[idx - 1] == "n" else f"[[{ref}]]"
    repl = re.sub(r"\{(\d*)\}", group, en.replace("\\", "\\\\"))
    return regex, repl


def _literal_len(de: str) -> int:
    return len(re.sub(r"\{#?\}", "", de))


_exact: dict[str, str] = {}
for _k, _v in EXACT.items():
    # identity entries only risk renaming drivers/teams; ALL-CAPS keys must not shadow the normal spelling
    if _k == _v or (_k.isupper() and _k.lower() in _exact):
        continue
    _exact[_k.lower()] = _v
_patterns: list[tuple[re.Pattern[str], str | Callable[[re.Match[str]], str]]] = [
    (re.compile(p, re.IGNORECASE | re.DOTALL), r) for p, r in PATTERNS]
_patterns += [(re.compile(rx, re.IGNORECASE | re.DOTALL), rp) for rx, rp in
              (compile_template(de, en) for de, en in sorted(TEMPLATES, key=lambda t: -_literal_len(t[0])))]
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
    if letters and letters[0].isupper() and out[:1].islower():
        return out[:1].upper() + out[1:]
    if src[:1].islower() and out[:1].isupper() and out[1:2].islower():
        return out[:1].lower() + out[1:]
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
