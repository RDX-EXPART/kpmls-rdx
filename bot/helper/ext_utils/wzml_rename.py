"""
WZML-X Auto Rename Engine — ported to KPSML-X
==============================================
Provides:
  fetch_extra_info()        — parse filename → MediaInfo (Name/Season/Episode/Quality/OTT/Audio/Lib...)
  extract_season_episode()  — parse SxxExx patterns
  sanitize_filename()       — clean forbidden chars from filename
  clean_name()              — strip common site-tags / underscores
  safe_format()             — KeyError-safe str.format_map
  get_video_bit_codec()     — ffprobe → (bit_depth, codec)  e.g. ("10Bit", "x265")
  MediaInfo                 — simple dataclass returned by fetch_extra_info
"""

from __future__ import annotations
import re
import unicodedata
from dataclasses import dataclass, field
from os import path as ospath
from typing import List

# ──────────────────────────────────────────────────────────────────────────────
#  SafeDict — missing keys become empty string (never raise KeyError)
# ──────────────────────────────────────────────────────────────────────────────

class _SafeDict(dict):
    def __missing__(self, key):
        return ""

def safe_format(text: str, **kwargs) -> str:
    """str.format_map but missing placeholders become empty string."""
    return text.format_map(_SafeDict(**kwargs))


# ──────────────────────────────────────────────────────────────────────────────
#  MediaInfo dataclass
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class MediaInfo:
    AutoRename: bool = False
    Name: str = ""
    Year: str = ""
    Season: str = ""
    Start_Episode: str = ""
    End_Episode: str = ""
    Part: str = ""
    Audio: str = ""
    Quality: str = ""
    Resolution: str = ""
    Ott: str = ""
    Languages: List[str] = field(default_factory=list)
    Lib: str = ""
    Subtitle: str = ""


# ──────────────────────────────────────────────────────────────────────────────
#  clean_name
# ──────────────────────────────────────────────────────────────────────────────

def clean_name(filename: str, remove_emoji: bool = True) -> str:
    if not isinstance(filename, str) or not filename:
        return ""

    original = filename.strip()

    if "." in original:
        name_part, ext = original.rsplit(".", 1)
        ext = "." + ext
    else:
        name_part = original
        ext = ""

    def _strip_emoji(text: str) -> str:
        try:
            text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
        except Exception:
            pass
        return text

    if remove_emoji:
        name_part = _strip_emoji(name_part)

    patterns = [
        r"@\w+",
        r"https?://\S+|t\.me/\S+|www\.\S+",
        r"#\w+",
        r"\b(?:HDHub4u|MoviesVerse|FilmyZilla|KatMovieHD|Worldfree4u|9xmovies|ExtraFlix|PrimeFix|mkvCinemas|Toonworld4all)\b",
    ]
    combined = "|".join(f"(?:{p})" for p in patterns)
    name_part = re.sub(combined, "", name_part, flags=re.IGNORECASE)

    name_part = name_part.replace("_", " ").replace("+", " ")
    name_part = re.sub(r"\.+", " ", name_part)
    name_part = re.sub(r"[\[\]\(\)\{\}]", "", name_part)
    name_part = re.sub(r"\s+", " ", name_part).strip()

    return f"{name_part or original}{ext}"


# ──────────────────────────────────────────────────────────────────────────────
#  sanitize_filename — remove chars forbidden on Windows/Unix FS
# ──────────────────────────────────────────────────────────────────────────────

def sanitize_filename(name: str, default_extension: str = "") -> str:
    if not name:
        return "default_filename" + default_extension

    lines = [l.strip() for l in name.splitlines() if l.strip()]
    if not lines:
        return "default_filename" + default_extension

    filename_line = lines[0]
    base, ext = ospath.splitext(filename_line)
    base = base.strip()

    if not ext or len(ext) > 5:
        for line in lines[1:]:
            _, line_ext = ospath.splitext(line)
            if line_ext and len(line_ext) <= 5:
                ext = line_ext
                break

    base = re.sub(r"<[^>]+>", "", base)
    base = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", base)
    base = re.sub(r'[<>:"|?*\0/\\]', "", base)
    base = re.sub(r"\s+", " ", base).strip()
    base = base.rstrip(". ")
    base = base.lstrip(".")

    if len(base) > 250:
        base = base[:250].rstrip(". ")

    if not ext:
        ext = default_extension
    if not base:
        base = "default_filename"

    return base + ext


# ──────────────────────────────────────────────────────────────────────────────
#  Season / Episode extractor
# ──────────────────────────────────────────────────────────────────────────────

def extract_season_episode(filename: str):
    """Return (Season, Start_Episode, End_Episode) as formatted strings."""
    file_name = clean_name(filename)
    Season = Start_Episode = End_Episode = ""

    # SxxExx  /  SxxExx-Exx  /  SxxExx.Eyy
    combined = re.search(
        r"\bS(\d{1,2})E(\d{1,3})(?:[-._]E?(\d{1,3}))?\b", file_name, re.IGNORECASE
    )
    if combined:
        Season        = f"S{int(combined.group(1)):02d}"
        Start_Episode = f"E{int(combined.group(2)):02d}"
        if combined.group(3):
            End_Episode = f"E{int(combined.group(3)):02d}"
        return Season, Start_Episode, End_Episode

    # Separate Season / Episode tags
    season_m = re.search(r"\b(?:S|Season)\s*(\d{1,2})\b", file_name, re.IGNORECASE)
    if season_m:
        Season = f"S{int(season_m.group(1)):02d}"

    ep_pat = re.compile(
        r"\b(?:E|EP|Episode)\s*(\d{1,3})"
        r"(?:\s*(?:to|-|T|\.|_)\s*(?:E)?(\d{1,3}))?"
        r"|E(\d{1,3})E(\d{1,3})\b",
        re.IGNORECASE,
    )
    ep_m = ep_pat.search(file_name)
    if ep_m:
        if ep_m.group(1):
            Start_Episode = f"E{int(ep_m.group(1)):02d}"
            if ep_m.group(2):
                End_Episode = f"E{int(ep_m.group(2)):02d}"
        elif ep_m.group(3):
            Start_Episode = f"E{int(ep_m.group(3)):02d}"
            End_Episode   = f"E{int(ep_m.group(4)):02d}"

    return Season, Start_Episode, End_Episode


# ──────────────────────────────────────────────────────────────────────────────
#  fetch_extra_info — main metadata extractor
# ──────────────────────────────────────────────────────────────────────────────

_LANGUAGES = [
    "Hindi", "English", "Tamil", "Telugu", "Malayalam", "Kannada", "Marathi",
    "Bengali", "Gujarati", "Bhojpuri", "Odia", "Punjabi", "Urdu",
    "Spanish", "French", "German", "Chinese", "Japanese", "Korean",
    "Italian", "Portuguese", "Russian",
]

_QUALITIES = [
    "SDTV-Rip", "HDTV-Rip", "SDTV", "HDTV", "SDTVRip", "HDTVRip", "DVDScr",
    "PRE-HD", "WEBDL", "WEB-DL", "WEB DL", "WEBRip", "BluRay", "HDRip",
    "PreDVD", "DVDRip", "YTRip", "HDTS", "HDTC", "CAMRip", "HQSprint",
    "HDCAM", "HDCAMRip", "TELESYNC", "TSQRip", "BRRip", "HQ SPrint",
]

_OTT_PLATFORMS = [
    "NF", "AMZN", "HBO", "JioHotstar", "JioHS", "JHS", "DSNP", "HS", "CR",
    "JC", "Jio", "PF", "VOD", "BMS", "CRAV", "MX", "ATVP", "MAX", "PCOK",
    "SONYLiv", "ZEE5", "SS", "APLVTV", "HULU", "APL", "YT", "STZ", "STARZ",
    "PS", "AHA",
]

_RESOLUTIONS = ["360p", "480p", "720p", "1080p", "4K", "2K", "144p", "240p", "2160p", "576p"]

_EMPTY = MediaInfo(AutoRename=False)


def fetch_extra_info(filename: str) -> MediaInfo:
    """Parse *filename* and return a populated MediaInfo.

    AutoRename=True  → metadata was successfully extracted
    AutoRename=False → filename doesn't look like a media release
    """
    if not filename:
        return _EMPTY

    cleaned = re.sub(r"[\_\s+\(\)]", " ", filename)
    file_name = clean_name(cleaned)

    # ── Resolution ────────────────────────────────────────────────────────────
    detected_res = []
    for r in _RESOLUTIONS:
        pat = r.replace(".", r"\.").replace("K", "[Kk]")
        if re.search(rf"\b{pat}\b", file_name, re.IGNORECASE):
            detected_res.append(r)
    Resolution = " ".join(detected_res)

    # ── Audio ─────────────────────────────────────────────────────────────────
    audio_pat = re.compile(
        r"\b(?:AAC|DD|DDP|Opus|AC3)\s?(?:\d{1,2}(?:\.\d+)?)?(?:\s?Atmos)?\b|\b(?:\d+CH)\b",
        re.IGNORECASE,
    )
    fname_dot = filename.replace("_", ".")
    audio_matches = audio_pat.findall(fname_dot)
    Audio = " ".join(audio_matches) if audio_matches else "AAC"

    # ── Languages ─────────────────────────────────────────────────────────────
    lang_pats = [re.compile(r"\b" + re.escape(lg) + r"\b", re.IGNORECASE) for lg in _LANGUAGES]
    Languages = [lg for pat, lg in zip(lang_pats, _LANGUAGES) if pat.search(file_name)]

    # ── Year ──────────────────────────────────────────────────────────────────
    year_m = re.search(r"\b(19[0-9]{2}|20[0-9]{2})\b", file_name)
    Year = str(int(year_m.group(1))) if year_m else ""

    # ── Quality ───────────────────────────────────────────────────────────────
    q_pats = [re.compile(r"\b" + re.escape(q) + r"\b", re.IGNORECASE) for q in _QUALITIES]
    Quality = ""
    for pat, orig in zip(q_pats, _QUALITIES):
        if pat.search(file_name):
            Quality = orig
            break

    # ── OTT platform ──────────────────────────────────────────────────────────
    ott_pats = [
        re.compile(r"\b" + re.escape(p) + r"\b(?=\s|$)", re.IGNORECASE)
        for p in _OTT_PLATFORMS
    ]
    Ott = ""
    for pat, orig in zip(ott_pats, _OTT_PLATFORMS):
        if pat.search(file_name) and Quality.lower().strip() != "bluray":
            Ott = orig
            break

    # ── Subtitle ──────────────────────────────────────────────────────────────
    sub_m = re.search(r"\b(?:HC-)?(?:[A-Za-z]{1,2}-)?[EeMm]sub\b", file_name, re.IGNORECASE)
    Subtitle = f" {sub_m.group(0)}" if sub_m else ""

    # ── Codec/Lib ─────────────────────────────────────────────────────────────
    lib_pat = re.compile(r"(x264|x265|H\.264|H\.265)", re.IGNORECASE)
    Lib = ""
    if lib_m := lib_pat.search(file_name):
        codec = lib_m.group(0).lower()
        Lib = "x265" if "265" in codec else "x264"

    # ── Part ──────────────────────────────────────────────────────────────────
    part_m = re.search(r"\.part(\d{1,3})\b", file_name, re.IGNORECASE)
    Part = part_m.group(1) if part_m else ""

    # ── Season / Episode ──────────────────────────────────────────────────────
    Season, Start_Episode, End_Episode = extract_season_episode(file_name)

    # ── Name ──────────────────────────────────────────────────────────────────
    name_pat = re.compile(
        r"^(.*?)(?=\s*(?:S\d+E\d+|S\d+|E\d+|\d{4}(?!\d)|\d+p|$))", re.IGNORECASE
    )
    name_m = name_pat.search(file_name)
    Name = name_m.group(1).rstrip(". ") if name_m else file_name

    # Decide AutoRename: require at least a non-empty Name
    auto = bool(Name and Name.strip())

    return MediaInfo(
        AutoRename=auto,
        Name=Name,
        Year=Year,
        Season=Season,
        Start_Episode=Start_Episode,
        End_Episode=End_Episode,
        Part=Part,
        Audio=Audio,
        Quality=Quality,
        Resolution=Resolution,
        Ott=Ott,
        Languages=Languages,
        Lib=Lib,
        Subtitle=Subtitle,
    )


# ──────────────────────────────────────────────────────────────────────────────
#  get_video_bit_codec — ffprobe → ("10Bit", "x265") etc.
# ──────────────────────────────────────────────────────────────────────────────

async def get_video_bit_codec(path: str):
    """Return (bit_depth_str, codec_str) from ffprobe, e.g. ("10Bit", "x265").
    Falls back to ("", "") on any error or non-video file.
    """
    try:
        from bot.helper.ext_utils.bot_utils import cmd_exec
        result = await cmd_exec([
            "ffprobe", "-hide_banner", "-loglevel", "error",
            "-print_format", "json", "-show_streams", path,
        ])
    except Exception:
        return "", ""

    if not result[0] or result[2] != 0:
        return "", ""

    try:
        data = eval(result[0])
    except Exception:
        return "", ""

    for stream in data.get("streams", []):
        if stream.get("codec_type") != "video":
            continue
        pix_fmt = stream.get("pix_fmt", "")
        bit = ""
        if "10" in pix_fmt:
            bit = "10Bit"
        elif "12" in pix_fmt:
            bit = "12Bit"
        elif "8" in pix_fmt:
            bit = "8Bit"

        codec_map = {"h264": "x264", "hevc": "x265", "av1": "AV1", "vp9": "VP9"}
        codec = codec_map.get(stream.get("codec_name", ""), stream.get("codec_name", ""))
        return bit, codec

    return "", ""
