#!/usr/bin/env python3
"""Auto thumbnail helper using GK thumb API.

Flow:
- Clean movie/series title from file name or URL
- Call: {GK_API_URL}/api/thumb?name=<title>
- Download returned poster/thumb URL as a local jpg
"""
from os import path as ospath
from re import sub, search
from urllib.parse import quote_plus, urlparse, unquote

from aiofiles.os import path as aiopath, makedirs, remove as aioremove
from PIL import Image

from bot import GK_API_URL, LOGGER
from bot.helper.utils import request
from bot.helper.ext_utils.bot_utils import download_image_url, sync_to_async

_QUALITY_WORDS = r"(2160p|1080p|720p|480p|360p|4k|8k|uhd|hdrip|webrip|web[-_. ]?dl|bluray|brrip|dvdrip|hdtv|x264|x265|hevc|10bit|aac|ddp?5?\.?1|esub|multi|hin|eng|hindi|english|dual[-_. ]?audio)"


def clean_thumb_name(name: str) -> str:
    """Convert a URL or media filename into a searchable title for thumb API."""
    raw = str(name or "").strip()
    if not raw:
        return ""

    # URL support: https://www.themoviedb.org/tv/85552-euphoria -> euphoria
    if raw.startswith(("http://", "https://")):
        parsed = urlparse(raw)
        raw = parsed.path.strip("/").split("/")[-1] or parsed.netloc
        raw = unquote(raw)

    base = ospath.basename(raw)
    base = sub(r"\.(mkv|mp4|avi|mov|wmv|flv|webm|m4v|mp3|m4a|flac|zip|rar)$", "", base, flags=2)
    base = base.replace("_", " ").replace(".", " ").replace("-", " ")

    # Remove season/episode and common release tags.
    base = sub(r"\bS\d{1,2}E\d{1,3}\b", " ", base, flags=2)
    base = sub(r"\bS\d{1,2}\b|\bE\d{1,3}\b", " ", base, flags=2)
    base = sub(r"\b(19|20)\d{2}\b", " ", base)
    base = sub(_QUALITY_WORDS, " ", base, flags=2)
    base = sub(r"\[[^\]]+\]|\([^\)]+\)", " ", base)
    base = sub(r"\b\d+\b", " ", base)
    base = sub(r"\s+", " ", base).strip()
    return base[:80]


def _extract_thumb_url(data):
    if not isinstance(data, dict):
        return None
    for key in ("thumb", "poster", "image", "url", "download_url"):
        val = data.get(key)
        if isinstance(val, str) and val.startswith(("http://", "https://")):
            return val
    # Some APIs may return list of posters.
    for key in ("posters", "results", "images"):
        val = data.get(key)
        if isinstance(val, list):
            for item in val:
                if isinstance(item, str) and item.startswith(("http://", "https://")):
                    return item
                if isinstance(item, dict):
                    for k in ("thumb", "poster", "image", "url"):
                        v = item.get(k)
                        if isinstance(v, str) and v.startswith(("http://", "https://")):
                            return v
    return None


async def get_auto_thumb(search_name: str):
    title = clean_thumb_name(search_name)
    if not title:
        return None
    api = f"{GK_API_URL}/api/thumb?name={quote_plus(title)}"
    try:
        data = await request(api)
        thumb_url = _extract_thumb_url(data)
        if not thumb_url:
            LOGGER.info(f"[AUTO_THUMB] No image found for: {title}")
            return None
        temp_path = await download_image_url(thumb_url)
        if not temp_path or not await aiopath.exists(temp_path):
            return None
        await makedirs("Thumbnails", exist_ok=True)
        out_path = ospath.join("Thumbnails", f"auto_{abs(hash(title))}.jpg")
        try:
            await sync_to_async(Image.open(temp_path).convert("RGB").save, out_path, "JPEG")
        finally:
            try:
                await aioremove(temp_path)
            except Exception:
                pass
        return out_path if await aiopath.exists(out_path) else None
    except Exception as e:
        LOGGER.error(f"[AUTO_THUMB] Error for {title}: {e}")
        return None


async def get_auto_thumb_for_file(file_path: str):
    return await get_auto_thumb(ospath.basename(str(file_path)))
