# smart_rename.py
# Dynamic language rename for movies/series filenames (world languages support)
# - Detects languages from ISO codes + common names via aliases
# - Dual Audio for 2 langs, Multi Audio for 3+ langs
# - Prevents duplicate "Dual/Multi Audio"
# - Normalizes WEB-DL, resolution and removes junk tags

import re
from typing import List, Tuple

try:
    from langcodes import Language
except Exception:
    Language = None  # if not installed, fallback to alias-only


# -------------------- CONFIG --------------------

JUNK_PATTERNS = [
    r"\bx264\b", r"\bx265\b", r"\bhevc\b", r"\bh\.?265\b", r"\bh\.?264\b",
    r"\baac\b", r"\bac3\b", r"\bdts\b", r"\batmos\b",
    r"\besub\b", r"\bsubs?\b", r"\bsubtitles?\b",
    r"\bbluray\b", r"\bwebrip\b", r"\bhdrip\b", r"\bdvdrip\b",
    r"\bproper\b", r"\brepack\b",
    r"\bvega[a-z]*movies\b", r"\bvegamovies\b", r"\bhot\b",
    r"\bmxplayer\b", r"\btelegram\b", r"\btg\b",
]

# Common alias names -> normalized
# (এখানে আপনার দরকার অনুযায়ী আরও alias যোগ করতে পারবেন)
LANG_ALIASES = {
    # South Asia
    "hindi": "Hindi", "hin": "Hindi",
    "english": "English", "eng": "English",
    "tamil": "Tamil", "tam": "Tamil",
    "telugu": "Telugu", "tel": "Telugu",
    "kannada": "Kannada", "kan": "Kannada",
    "malayalam": "Malayalam", "mal": "Malayalam",
    "bengali": "Bengali", "ben": "Bengali", "bangla": "Bengali",
    "marathi": "Marathi", "mar": "Marathi",
    "punjabi": "Punjabi", "pan": "Punjabi",
    "gujarati": "Gujarati", "guj": "Gujarati",
    "urdu": "Urdu", "urd": "Urdu",

    # Popular world languages
    "spanish": "Spanish", "spa": "Spanish", "es": "Spanish",
    "french": "French", "fra": "French", "fre": "French", "fr": "French",
    "german": "German", "deu": "German", "ger": "German", "de": "German",
    "italian": "Italian", "ita": "Italian", "it": "Italian",
    "portuguese": "Portuguese", "por": "Portuguese", "pt": "Portuguese",
    "russian": "Russian", "rus": "Russian", "ru": "Russian",
    "turkish": "Turkish", "tur": "Turkish", "tr": "Turkish",
    "arabic": "Arabic", "ara": "Arabic", "ar": "Arabic",
    "persian": "Persian", "farsi": "Persian", "fas": "Persian", "per": "Persian", "fa": "Persian",

    # Chinese variants
    "chinese": "Chinese", "mandarin": "Chinese",
    "zho": "Chinese", "chi": "Chinese", "zh": "Chinese",

    # Filipino
    "filipino": "Filipino", "tagalog": "Filipino",
    "fil": "Filipino", "tgl": "Filipino",

    # Japanese / Korean
    "japanese": "Japanese", "jpn": "Japanese", "ja": "Japanese",
    "korean": "Korean", "kor": "Korean", "ko": "Korean",

    # Indonesian / Malay
    "indonesian": "Indonesian", "ind": "Indonesian", "id": "Indonesian",
    "malay": "Malay", "msa": "Malay", "may": "Malay", "ms": "Malay",

    # Thai / Vietnamese
    "thai": "Thai", "tha": "Thai", "th": "Thai",
    "vietnamese": "Vietnamese", "vie": "Vietnamese", "vi": "Vietnamese",

    # Dutch / Swedish / Norwegian / Danish / Finnish / Greek
    "dutch": "Dutch", "nld": "Dutch", "dut": "Dutch", "nl": "Dutch",
    "swedish": "Swedish", "swe": "Swedish", "sv": "Swedish",
    "norwegian": "Norwegian", "nor": "Norwegian", "no": "Norwegian",
    "danish": "Danish", "dan": "Danish", "da": "Danish",
    "finnish": "Finnish", "fin": "Finnish", "fi": "Finnish",
    "greek": "Greek", "ell": "Greek", "gre": "Greek", "el": "Greek",

    # Hebrew / Polish / Romanian / Hungarian / Czech
    "hebrew": "Hebrew", "heb": "Hebrew", "he": "Hebrew",
    "polish": "Polish", "pol": "Polish", "pl": "Polish",
    "romanian": "Romanian", "ron": "Romanian", "rum": "Romanian", "ro": "Romanian",
    "hungarian": "Hungarian", "hun": "Hungarian", "hu": "Hungarian",
    "czech": "Czech", "ces": "Czech", "cze": "Czech", "cs": "Czech",
}

# Prefer this order for output if found (rest will be appended alphabetically)
LANG_ORDER = [
    "Hindi", "English", "Tamil", "Telugu", "Kannada", "Malayalam",
    "Bengali", "Marathi", "Punjabi", "Gujarati", "Urdu",
    "Arabic", "Persian", "Turkish", "Russian", "Chinese", "Japanese", "Korean",
    "Spanish", "French", "German", "Italian", "Portuguese",
    "Indonesian", "Malay", "Thai", "Vietnamese",
    "Dutch", "Swedish", "Norwegian", "Danish", "Finnish", "Greek",
    "Hebrew", "Polish", "Romanian", "Hungarian", "Czech",
    "Filipino",
]

VIDEO_EXT_RE = re.compile(r"(?i)\.(mkv|mp4|avi|mov|wmv|m4v)$")
RES_RE = re.compile(r"(?i)\b(480p|540p|720p|1080p|1440p|2160p|4320p|4k)\b")
WEB_DL_RE = re.compile(r"(?i)\bweb\s*[- ]?\s*dl\b")
SERIES_RE = re.compile(
    r"(?i)\bS\d{1,2}\s*E\d{1,2}\b|\bSeason\s*\d+\b|\bEp(?:isode)?\s*\d+\b|\bE\d{1,3}\b"
)
AUDIO_TAG_RE = re.compile(r"(?i)\b(Dual\s*Audio|Multi\s*Audio)\b")


# -------------------- HELPERS --------------------

def is_series(name: str) -> bool:
    return bool(SERIES_RE.search(name or ""))


def split_ext(filename: str) -> Tuple[str, str]:
    filename = (filename or "").strip()
    m = VIDEO_EXT_RE.search(filename)
    if not m:
        return filename, ""
    ext = "." + m.group(1).lower()
    base = filename[: m.start()]
    return base, ext


def _normalize_separators(s: str) -> str:
    s = re.sub(r"[._]+", " ", s)
    s = re.sub(r"[-]+", " ", s)
    s = re.sub(r"\s{2,}", " ", s)
    return s.strip()


def _strip_brackets(s: str) -> str:
    return re.sub(r"[\[\]\(\)\{\}]", " ", s)


def _remove_junk(s: str) -> str:
    out = s
    for p in JUNK_PATTERNS:
        out = re.sub(rf"(?i){p}", " ", out)
    out = re.sub(r"\s{2,}", " ", out).strip()
    return out


def _lang_from_iso(token: str) -> str | None:
    """
    Try ISO detection using langcodes (supports thousands of languages).
    Only accept if it returns a real name and not "Unknown language".
    """
    if not Language:
        return None

    tok = token.lower()
    if len(tok) not in (2, 3):
        return None

    try:
        # "en" -> English, "rus" -> Russian, "zho" -> Chinese, "fil" -> Filipino etc.
        name = Language.get(tok).display_name()
        if not name:
            return None
        low = name.lower()
        if "unknown" in low:
            return None
        # Normalize like "English" / "Russian" etc.
        return name.split(" (", 1)[0].strip().title()
    except Exception:
        return None


def _extract_languages(raw: str) -> List[str]:
    """
    Extract languages from filename using:
    - alias map (names + common codes)
    - ISO code detection via langcodes (world languages)
    """
    t = _normalize_separators(raw)
    # get word tokens
    tokens = re.findall(r"(?i)\b[a-z]{2,20}\b", t)

    found: List[str] = []
    for tok in tokens:
        key = tok.lower()

        # alias match first
        if key in LANG_ALIASES:
            val = LANG_ALIASES[key]
            if val not in found:
                found.append(val)
            continue

        # ISO detection via langcodes (2 or 3 letters)
        iso_name = _lang_from_iso(key)
        if iso_name:
            # Some names come as "Chinese" already, keep
            if iso_name not in found:
                found.append(iso_name)

    # reorder by preferred order, rest alphabetically
    ordered = [x for x in LANG_ORDER if x in found]
    remaining = sorted([x for x in found if x not in ordered])
    return ordered + remaining


def _remove_language_tokens(s: str) -> str:
    """
    Remove language tokens (both aliases + ISO codes) so we can append clean audio tag once.
    """
    # Remove alias keys (like hindi, hin, eng, russian, rus, turkish, tur, chinese, zho, fil...)
    keys = sorted(set(LANG_ALIASES.keys()), key=len, reverse=True)
    pat_alias = r"(?i)\b(" + "|".join(re.escape(k) for k in keys) + r")\b"
    s = re.sub(pat_alias, " ", s)

    # Also remove 2-3 letter ISO codes (best-effort) to avoid leftovers like "en", "ru", "tr"
    # We only remove if langcodes recognizes OR token exists in aliases (handled above).
    # Here: remove any standalone 2-3 letters that look like codes (safe-ish).
    s = re.sub(r"(?i)\b[a-z]{2,3}\b", " ", s)

    return re.sub(r"\s{2,}", " ", s).strip()


def _apply_audio_tag(s: str, langs: List[str]) -> str:
    if not langs or len(langs) < 2:
        s = AUDIO_TAG_RE.sub(" ", s)
        return re.sub(r"\s{2,}", " ", s).strip()

    # remove any existing Dual/Multi
    s = AUDIO_TAG_RE.sub(" ", s)
    s = re.sub(r"(?i)\bdual\b|\bmulti\b", " ", s)
    s = re.sub(r"\s{2,}", " ", s).strip()

    tag = ("Dual Audio " if len(langs) == 2 else "Multi Audio ") + " ".join(langs)
    if not re.search(r"(?i)\b(Dual Audio|Multi Audio)\b", s):
        s = f"{s} {tag}".strip()
    return re.sub(r"\s{2,}", " ", s).strip()


def _title_clean(s: str) -> str:
    s = re.sub(r"\s{2,}", " ", s).strip()
    parts = s.split()
    out = []
    for w in parts:
        if w.upper() == "WEB-DL":
            out.append("WEB-DL")
        elif re.fullmatch(r"(?i)(480p|540p|720p|1080p|1440p|2160p|4320p|4k)", w):
            out.append("4K" if w.lower() == "4k" else w.lower())
        else:
            out.append(w[:1].upper() + w[1:].lower() if w else w)
    return " ".join(out).strip()


# -------------------- MAIN API --------------------

def smart_rename(filename: str, skip_series: bool = False) -> str:
    original = (filename or "").strip()
    if not original:
        return original

    if skip_series and is_series(original):
        return original

    base, ext = split_ext(original)
    s = base

    s = _normalize_separators(s)
    s = _strip_brackets(s)
    s = _normalize_separators(s)

    # Normalize WEB-DL
    had_webdl = bool(WEB_DL_RE.search(s))
    s = WEB_DL_RE.sub("WEB-DL", s)

    # resolution capture
    res_match = RES_RE.search(s)
    res_token = None
    if res_match:
        rt = res_match.group(1)
        res_token = "4K" if rt.lower() == "4k" else rt.lower()

    # Extract languages first
    langs = _extract_languages(s)

    # Remove language tokens + existing audio tags to prevent duplicates
    s = _remove_language_tokens(s)
    s = AUDIO_TAG_RE.sub(" ", s)
    s = re.sub(r"\s{2,}", " ", s).strip()

    # Remove junk
    s = _remove_junk(s)

    # Remove WEB-DL/res from middle (append at end)
    s = re.sub(r"(?i)\bWEB-DL\b", " ", s)
    s = RES_RE.sub(" ", s)
    s = re.sub(r"\s{2,}", " ", s).strip()

    s = _title_clean(s)

    # Add audio tag (Dual/Multi)
    s = _apply_audio_tag(s, langs)

    # Tail
    tail = []
    if had_webdl:
        tail.append("WEB-DL")
    if res_token:
        tail.append(res_token)

    final = (s + (" " if s and tail else "") + " ".join(tail)).strip()
    final = re.sub(r"\s{2,}", " ", final).strip()

    return final + ext


def smart_rename_movie(filename: str, skip_series: bool = True) -> str:
    return smart_rename(filename, skip_series=skip_series)


def smart_rename_series(filename: str) -> str:
    return smart_rename(filename, skip_series=False)
