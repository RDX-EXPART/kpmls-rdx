#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Smart rename for KPSML/WZML-X style leech bots.

Goal:
- Clean junk tags (x264, HEVC, ESub, site names, etc.)
- Normalize separators to spaces
- Detect/normalize: year, quality (480p/720p/1080p/2160p/4K), source tag (WEB-DL, WEBRip, BluRay, HDRip, etc.)
- Detect languages dynamically (Hindi/Tamil/Telugu/English/... many more) and add:
    - "Dual Audio <Lang1> <Lang2>" when exactly 2 languages
    - "Multi Audio <Lang1> <Lang2> <Lang3> ..." when 3+ languages
- Works for movie + series (skip_series flag)
"""

from __future__ import annotations

import re
from collections import OrderedDict
from typing import List, Tuple, Optional


# Common junk tokens / release groups / site tags
_JUNK_PATTERNS = [
    r"\bx264\b", r"\bx265\b", r"\bhevc\b", r"\bh\.?264\b", r"\bh\.?265\b",
    r"\b10bit\b", r"\b8bit\b", r"\baac(?:\d\.\d)?\b", r"\bdts\b", r"\bddp?(?:\d\.\d)?\b", r"\bac3\b",
    r"\besub\b", r"\bsubs?\b", r"\bsubbed\b", r"\bsubtitle(?:s)?\b",
    r"\bproper\b", r"\brepack\b",
    r"\b(web)?\-?dl\b",  # handled separately (we normalize), but remove duplicates later
    r"\bwebrip\b", r"\bweb\-?rip\b",
    r"\bbluray\b", r"\bbrrip\b", r"\bhdrip\b", r"\bdvdrip\b", r"\bhdcam\b", r"\bcamrip\b",
    r"\b(hdcam|cam|ts|telesync)\b",
    r"\b(etrg|yts|rarbg)\b",
    r"\b(?:www\.)\S+\b",
    # common site tags (extend as needed)
    r"\bvega[a-z]*movies\b", r"\bvegamovies\b", r"\bhot\b",
    r"\bmkvcinemas?\b", r"\bmoviesmod\b", r"\bhdhub4u\b", r"\bkatmoviehd\b",
    r"\btelegram\b", r"\btg\b",
]

# Language aliases -> canonical display name
# (Keep broad coverage; you can add more aliases anytime.)
_LANG_ALIASES = {
    # Indian
    "hindi": ["hindi", "hin", "hi"],
    "english": ["english", "eng", "en"],
    "tamil": ["tamil", "tam", "ta"],
    "telugu": ["telugu", "tel", "te"],
    "malayalam": ["malayalam", "mal", "ml"],
    "kannada": ["kannada", "kan", "kn"],
    "bengali": ["bengali", "bangla", "ben", "bn"],
    "marathi": ["marathi", "mar", "mr"],
    "punjabi": ["punjabi", "panjabi", "pa"],
    "gujarati": ["gujarati", "guj", "gu"],
    "urdu": ["urdu", "urd"],
    "nepali": ["nepali", "nep", "np"],
    "sinhala": ["sinhala", "sin", "si"],
    "assamese": ["assamese", "asm", "as"],
    "odia": ["odia", "oriya", "or"],
    "kashmiri": ["kashmiri", "kas"],
    # Middle East / Africa
    "arabic": ["arabic", "ara", "ar"],
    "persian": ["persian", "farsi", "fas", "fa"],
    "hebrew": ["hebrew", "heb", "he"],
    "turkish": ["turkish", "tur", "tr"],
    # East Asia
    "chinese": ["chinese", "chi", "zh", "mandarin", "cantonese"],
    "japanese": ["japanese", "jpn", "ja"],
    "korean": ["korean", "kor", "ko"],
    "thai": ["thai", "tha", "th"],
    "vietnamese": ["vietnamese", "vie", "vi"],
    "indonesian": ["indonesian", "indo", "ind", "id"],
    "malay": ["malay", "msa", "ms"],
    "filipino": ["filipino", "tagalog", "tgl", "fil"],
    # Europe
    "russian": ["russian", "rus", "ru"],
    "ukrainian": ["ukrainian", "ukr", "uk"],
    "polish": ["polish", "pol", "pl"],
    "german": ["german", "deu", "ger", "de"],
    "french": ["french", "fra", "fre", "fr"],
    "spanish": ["spanish", "spa", "es"],
    "italian": ["italian", "ita", "it"],
    "portuguese": ["portuguese", "por", "pt"],
    "dutch": ["dutch", "nld", "nl"],
    "swedish": ["swedish", "swe", "sv"],
    "norwegian": ["norwegian", "nor", "no"],
    "danish": ["danish", "dan", "da"],
    "greek": ["greek", "ell", "el"],
}

# Precompile language regex: matches whole tokens like "HIN", "Hindi", "Tamil" etc.
_LANG_TOKEN_RE = None


def _build_lang_token_re():
    parts = []
    for canon, aliases in _LANG_ALIASES.items():
        for a in aliases:
            parts.append(re.escape(a))
    # Order longer aliases first to avoid partial matches
    parts = sorted(set(parts), key=len, reverse=True)
    return re.compile(r"(?i)(?<![A-Za-z0-9])(" + "|".join(parts) + r")(?![A-Za-z0-9])")


_LANG_TOKEN_RE = _build_lang_token_re()


def is_series(name: str) -> bool:
    """Detect series patterns: S01E02 / Season 1 / E05 / Ep 05 / 1x02."""
    return bool(
        re.search(
            r"(?i)\bS\d{1,2}E\d{1,2}\b|\bSeason\s*\d+\b|\bEp(?:isode)?\s*\d+\b|\bE\d{1,3}\b|\b\d{1,2}x\d{1,2}\b",
            name,
        )
    )


def _normalize_source(s: str) -> Tuple[str, Optional[str]]:
    """
    Normalize source tags and return chosen source (WEB-DL/WEBRip/BluRay/HDRip/...).
    """
    source = None

    # Normalize web-dl variants
    if re.search(r"(?i)\bweb[\s\-]?dl\b", s):
        source = "WEB-DL"
        s = re.sub(r"(?i)\bweb[\s\-]?dl\b", "WEB-DL", s)

    # Normalize webrip variants (if no WEB-DL)
    if source is None and re.search(r"(?i)\bweb[\s\-]?rip\b|\bwebrip\b", s):
        source = "WEBRip"
        s = re.sub(r"(?i)\bweb[\s\-]?rip\b|\bwebrip\b", "WEBRip", s)

    # BluRay
    if source is None and re.search(r"(?i)\bblu[\s\-]?ray\b|\bbluray\b|\bbrrip\b", s):
        source = "BluRay"
        s = re.sub(r"(?i)\bblu[\s\-]?ray\b|\bbluray\b|\bbrrip\b", "BluRay", s)

    # HDRip
    if source is None and re.search(r"(?i)\bhdrip\b", s):
        source = "HDRip"
        s = re.sub(r"(?i)\bhdrip\b", "HDRip", s)

    # DVDRip
    if source is None and re.search(r"(?i)\bdvdrip\b", s):
        source = "DVDRip"
        s = re.sub(r"(?i)\bdvdrip\b", "DVDRip", s)

    return s, source


def _extract_languages(s: str) -> List[str]:
    """
    Extract languages in appearance order. Deduplicate.
    Supports tokens separated by dots/space/dash/slash/plus.
    """
    langs = OrderedDict()

    # First normalize separators to space so tokens become visible
    s2 = re.sub(r"[._\-+/]+", " ", s)

    # Scan tokens via regex
    for m in _LANG_TOKEN_RE.finditer(s2):
        tok = m.group(1).lower()
        for canon, aliases in _LANG_ALIASES.items():
            if tok in aliases:
                display = canon.title()
                # For "Chinese" we keep Chinese title-case; we are not splitting Mandarin/Cantonese separately
                if display not in langs:
                    langs[display] = True
                break

    # Special combined patterns
    # Example: HIN-ENG / Hindi-Eng / Hindi English etc.
    if re.search(r"(?i)\bhin\s*[- ]\s*eng\b|\bhindi\s*[- ]\s*eng(?:lish)?\b", s2):
        for d in ["Hindi", "English"]:
            langs.setdefault(d, True)

    return list(langs.keys())


def _remove_known_audio_tags(s: str) -> str:
    # Remove existing "Dual Audio" / "Multi Audio" / "Dubbed" tags to avoid duplicates
    s = re.sub(r"(?i)\b(dual|multi)\s*audio\b", " ", s)
    s = re.sub(r"(?i)\b(dubbed|dub)\b", " ", s)
    # Remove language lists like "Hindi English Tamil" if they were part of an older rename,
    # but we don't aggressively delete here to avoid removing true title words.
    return s


def smart_rename(filename: str, skip_series: bool = True) -> str:
    """
    Rename file (movie/series). Returns new filename (with extension).
    """
    original = filename.strip()

    if skip_series and is_series(original):
        return original

    # Extension (keep original case normalized to lower)
    ext = ""
    m = re.search(r"(?i)\.(mkv|mp4|avi|mov|m4v|ts)$", original)
    if m:
        ext = "." + m.group(1).lower()
        name = original[: m.start()]
    else:
        name = original

    s = name

    # Replace separators with spaces early
    s = re.sub(r"[._\-]+", " ", s)

    # Remove URLs quickly
    s = re.sub(r"(?i)\bwww\.\S+\b", " ", s)

    # Normalize source and remember it
    s, source = _normalize_source(s)

    # Extract year, quality
    year_m = re.search(r"\b(19\d{2}|20\d{2})\b", s)
    year = year_m.group(1) if year_m else None

    qual_m = re.search(r"(?i)\b(480p|540p|720p|1080p|2160p|4320p|4k)\b", s)
    quality = None
    if qual_m:
        q = qual_m.group(1)
        quality = "4K" if q.lower() == "4k" else q.lower()

    # Extract languages before removing junk
    langs = _extract_languages(s)

    # Remove existing audio tags (dual/multi) to avoid duplicates
    s = _remove_known_audio_tags(s)

    # Remove junk patterns
    for p in _JUNK_PATTERNS:
        s = re.sub(rf"(?i){p}", " ", s)

    # Remove brackets
    s = re.sub(r"[\[\]\(\)\{\}]", " ", s)

    # Cleanup spaces
    s = re.sub(r"\s{2,}", " ", s).strip()

    # Rebuild "audio tag"
    audio_tag = ""
    if len(langs) == 2:
        audio_tag = "Dual Audio " + " ".join(langs)
    elif len(langs) >= 3:
        audio_tag = "Multi Audio " + " ".join(langs)
    elif len(langs) == 1:
        # If only one language present, do nothing (keeps title cleaner)
        audio_tag = ""

    # Remove any language tokens from main title part so we don't repeat
    # This is conservative: remove exact language names (title-case) only if they appear as separate words.
    for lang in langs:
        s = re.sub(rf"(?i)(?<![A-Za-z0-9]){re.escape(lang)}(?![A-Za-z0-9])", " ", s)
    s = re.sub(r"\s{2,}", " ", s).strip()

    # Remove source / quality if present in middle; we will place at end
    if source:
        s = re.sub(rf"(?i)\b{re.escape(source)}\b", " ", s)
    if quality:
        s = re.sub(r"(?i)\b(480p|540p|720p|1080p|2160p|4320p|4k)\b", " ", s)

    s = re.sub(r"\s{2,}", " ", s).strip()

    # Ensure year stays near title (keep as part of s if found)
    # If year was stripped accidentally, re-add at end of title section (before tags)
    if year and not re.search(rf"\b{re.escape(year)}\b", s):
        # Put year after title words
        s = (s + " " + year).strip()

    # Tail parts in correct order
    tail_parts = []
    if audio_tag:
        tail_parts.append(audio_tag)
    if source:
        tail_parts.append(source)
    if quality:
        tail_parts.append(quality)

    final = (s + (" " if s and tail_parts else "") + " ".join(tail_parts)).strip()
    final = re.sub(r"\s{2,}", " ", final).strip()

    return final + ext


# Backward compatible alias for older code that used smart_rename_movie
def smart_rename_movie(filename: str, skip_series: bool = True) -> str:
    return smart_rename(filename, skip_series=skip_series)
