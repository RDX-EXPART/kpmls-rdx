#!/usr/bin/env python3
"""
AI Caption Generator for KPSML-X Leech Bot.

Automatically generates stylish captions for uploaded movies/series/anime
by parsing the filename and optionally fetching IMDB metadata.

Usage: Enabled via AI_CAPTION=True in config.env
       Customize via AI_CAPTION_TEMPLATE in config.env
"""

from re import search as re_search, sub as re_sub, IGNORECASE
from os import path as ospath
from aiofiles.os import path as aiopath

from bot import config_dict, LOGGER
from bot.helper.ext_utils.bot_utils import sync_to_async, get_readable_file_size


# ─────────────────────────────────────────────
#  Default caption template
#  Supported variables:
#    {title}        - Movie/series title
#    {year}         - Release year (e.g. 2025)
#    {year_str}     - " (2025)" or "" if unknown
#    {imdb_rating}  - IMDB rating or "N/A"
#    {imdb_line}    - Full IMDB line or "" if disabled/not found
#    {quality}      - Resolution + source (e.g. 1080p WEB-DL)
#    {languages}    - Audio languages (e.g. Hindi + English)
#    {audio}        - Audio codec (e.g. DD+5.1)
#    {file_size}    - Human-readable file size
#    {season}       - Season tag (e.g. S01) or ""
#    {episode}      - Episode tag (e.g. E05) or ""
#    {season_ep}    - Combined (e.g. S01E05) or ""
#    {genre}        - Genres (e.g. Action, Drama) or ""
#    {genre_line}   - Full genre line or ""
#    {filename}     - Raw filename (no extension)
# ─────────────────────────────────────────────

DEFAULT_AI_CAPTION_TEMPLATE = (
    "🎬 <b>{filename}</b>\n"
    "\n"
    "{imdb_line}"
    "🎞 <b>Quality:</b> {quality}\n"
    "🔊 <b>Audio:</b> {languages}\n"
    "📦 <b>Size:</b> {file_size}"
    "{season_ep_line}"
    "{genre_line}"
)


def _build_quality_str(meta: dict) -> str:
    """Combine resolution + quality source into one readable string."""
    resolution = meta.get('resolution', '')
    quality = meta.get('quality', '')
    ott = meta.get('ott', '')

    parts = []
    if resolution:
        parts.append(resolution)
    if quality:
        parts.append(quality)
    if ott:
        parts.append(ott)

    if parts:
        return ' '.join(parts)
    return 'Unknown'


def _build_languages_str(meta: dict) -> str:
    """Build a readable language string like 'Hindi + English'."""
    langs = meta.get('languages', '') or meta.get('shortlang', '')
    if not langs:
        return 'Unknown'
    lang_list = [l.strip() for l in langs.replace(',', ' ').split() if l.strip()]
    seen = []
    for lg in lang_list:
        if lg not in seen:
            seen.append(lg)
    return ' + '.join(seen) if seen else 'Unknown'


async def _fetch_imdb_data(title: str, year: str = '') -> dict | None:
    """
    Fetch movie/series info from IMDB using cinemagoer.
    Returns a dict with keys: title, year, rating, genres, kind.
    Returns None on failure or if IMDB lookup is disabled.
    """
    if not config_dict.get('AI_CAPTION_IMDB', True):
        return None
    if not title or len(title.strip()) < 2:
        return None

    try:
        from imdb import Cinemagoer
        ia = Cinemagoer()

        search_query = f"{title} {year}".strip() if year else title
        results = await sync_to_async(ia.search_movie, search_query)

        if not results:
            return None

        movie = results[0]

        # Prefer exact year match within first 5 results
        if year:
            try:
                target_year = int(year)
                for r in results[:5]:
                    if r.get('year') == target_year:
                        movie = r
                        break
            except (ValueError, TypeError):
                pass

        # Fetch full details (rating, genres, etc.)
        await sync_to_async(ia.update, movie, ['main'])

        return {
            'title': movie.get('title', title),
            'year': str(movie.get('year', year or '')),
            'rating': movie.get('rating'),
            'genres': movie.get('genres', []),
            'kind': movie.get('kind', ''),
        }

    except ImportError:
        LOGGER.warning("AI Caption: 'cinemagoer' not installed. Install it via: pip install cinemagoer")
        return None
    except Exception as e:
        LOGGER.warning(f"AI Caption IMDB fetch failed for '{title}': {e}")
        return None


async def generate_ai_caption(
    filename: str,
    file_size: int,
    dirpath: str = None,
    meta: dict = None,
) -> str | None:
    """
    Generate a stylish AI caption for a leeched file.

    Args:
        filename:  Raw filename (with extension).
        file_size: File size in bytes.
        dirpath:   Parent directory path (used for ffprobe metadata).
        meta:      Pre-parsed filename metadata dict (optional).

    Returns:
        Formatted HTML caption string, or None on failure.
    """
    try:
        template = config_dict.get('AI_CAPTION_TEMPLATE', '').strip() or DEFAULT_AI_CAPTION_TEMPLATE

        # Parse filename if metadata not already provided
        if meta is None:
            from bot.helper.ext_utils.leech_utils import _rdx_parse_fields
            meta = _rdx_parse_fields(filename)

        # ── Basic fields from filename parser ──────────────────
        title = (meta.get('name') or ospath.splitext(filename)[0]).strip()
        year = meta.get('year', '')
        season = meta.get('season', '')
        episode = meta.get('episode', '')
        quality_str = _build_quality_str(meta)
        languages_str = _build_languages_str(meta)
        audio = meta.get('audio', '')
        size_str = get_readable_file_size(file_size) if isinstance(file_size, int) else str(file_size)

        # ── Try to enrich with ffprobe media info ──────────────
        if dirpath:
            try:
                from bot.helper.ext_utils.leech_utils import get_media_info
                up_path = ospath.join(dirpath, filename)
                if await aiopath.exists(up_path):
                    dur, qual, lang, subs = await get_media_info(up_path, True)
                    if qual and meta.get('resolution', '') == '':
                        quality_str = f"{qual} {meta.get('quality', '')}".strip() or qual
                    if lang:
                        probe_langs = [l.strip() for l in lang.split(',') if l.strip()]
                        existing_langs = [l.strip() for l in languages_str.split('+') if l.strip() and l.strip() != 'Unknown']
                        merged = existing_langs.copy()
                        for lg in probe_langs:
                            if lg not in merged:
                                merged.append(lg)
                        if merged:
                            languages_str = ' + '.join(merged)
            except Exception as e:
                LOGGER.debug(f"AI Caption ffprobe enrichment skipped: {e}")

        # ── IMDB fetch ─────────────────────────────────────────
        imdb_data = None
        if config_dict.get('AI_CAPTION_IMDB', True):
            imdb_data = await _fetch_imdb_data(title, year)

        # ── Build display values ───────────────────────────────
        if imdb_data:
            display_title = imdb_data.get('title', title)
            display_year = imdb_data.get('year', year)
            imdb_rating = imdb_data.get('rating')
            genres = imdb_data.get('genres', [])
        else:
            display_title = title
            display_year = year
            imdb_rating = None
            genres = []

        year_str = f" ({display_year})" if display_year else ""
        imdb_line = f"🌟 <b>IMDB:</b> {imdb_rating}\n" if imdb_rating else ""

        # Season + Episode
        season_ep = ''
        if season and episode:
            season_ep = f"{season}{episode}"
        elif season:
            season_ep = season
        season_ep_line = f"\n📺 <b>Episode:</b> {season_ep}" if season_ep else ""

        # Genre
        genre_str = ', '.join(genres[:3]) if genres else ''
        genre_line = f"\n🎭 <b>Genre:</b> {genre_str}" if genre_str else ""

        # ── Render template ────────────────────────────────────
        caption = template.format(
            title=display_title,
            year=display_year or '',
            year_str=year_str,
            imdb_rating=imdb_rating if imdb_rating is not None else 'N/A',
            imdb_line=imdb_line,
            quality=quality_str,
            languages=languages_str,
            audio=audio or '',
            file_size=size_str,
            season=season or '',
            episode=episode or '',
            season_ep=season_ep,
            season_ep_line=season_ep_line,
            genre=genre_str,
            genre_line=genre_line,
            filename=ospath.splitext(filename)[0],
        )

        # Clean up any stray empty lines from unused optional fields
        lines = caption.split('\n')
        cleaned_lines = []
        prev_blank = False
        for line in lines:
            is_blank = line.strip() == ''
            if is_blank and prev_blank:
                continue
            cleaned_lines.append(line)
            prev_blank = is_blank

        return '\n'.join(cleaned_lines).strip()

    except Exception as e:
        LOGGER.error(f"AI Caption generation failed for '{filename}': {e}")
        return None
