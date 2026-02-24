import re

JUNK_PATTERNS = [
    r"\bx264\b", r"\bx265\b", r"\bhevc\b", r"\besub\b",
    r"\bvega[a-z]*movies\b", r"\bvegamovies\b", r"\bhot\b",
]

def is_series(name: str) -> bool:
    # S01E02 / Season 1 / E05 / Ep 05
    return bool(re.search(r"(?i)\bS\d{1,2}E\d{1,2}\b|\bSeason\s*\d+\b|\bEp(?:isode)?\s*\d+\b|\bE\d{1,3}\b", name))

def smart_rename_movie(filename: str, skip_series: bool = True) -> str:
    original = filename

    if skip_series and is_series(original):
        return original

    # Extension
    ext = ""
    m = re.search(r"(?i)\.(mkv|mp4|avi)$", original.strip())
    if m:
        ext = "." + m.group(1).lower()
        name = original[:m.start()]
    else:
        name = original

    s = name

    # separators -> space
    s = re.sub(r"[._-]+", " ", s)

    # Dual audio normalize
    s = re.sub(r"(?i)\bhin\s*eng\b|\bhin\s*-\s*eng\b|\bhindi\s*eng(?:lish)?\b", "Dual Audio Hindi English", s)

    # WEB-DL normalize
    s = re.sub(r"(?i)\bweb\s*dl\b", "WEB-DL", s)

    # Remove junk words
    for p in JUNK_PATTERNS:
        s = re.sub(rf"(?i){p}", "", s)

    # Remove extra leftover tokens like brackets
    s = re.sub(r"[\[\]\(\)\{\}]", " ", s)

    # Clean multiple spaces
    s = re.sub(r"\s{2,}", " ", s).strip()

    # Try to capture year + resolution
    year = re.search(r"\b(19\d{2}|20\d{2})\b", s)
    res  = re.search(r"\b(480p|720p|1080p|2160p|4k)\b", s, re.I)

    # Ensure WEB-DL present if it was in source
    has_webdl = bool(re.search(r"(?i)\bWEB-DL\b", s))
    has_dual  = bool(re.search(r"(?i)\bDual Audio Hindi English\b", s))

    # Remove existing WEB-DL and resolution from middle (we’ll place at end)
    s2 = re.sub(r"(?i)\bWEB-DL\b", "", s)
    s2 = re.sub(r"(?i)\b(480p|720p|1080p|2160p|4k)\b", "", s2)
    s2 = re.sub(r"\s{2,}", " ", s2).strip()

    tail = []
    if has_dual:
        tail.append("Dual Audio Hindi English")
    if has_webdl:
        tail.append("WEB-DL")
    if res:
        tail.append(res.group(1).upper() if res.group(1).lower() == "4k" else res.group(1).lower())

    final = (s2 + (" " if s2 and tail else "") + " ".join(tail)).strip()
    final = re.sub(r"\s{2,}", " ", final).strip()

    return final + ext
