#!/usr/bin/env python3
from asyncio import Future, TimeoutError, wait_for
from time import time
from html import escape
from os import path as ospath, environ
from re import sub, search, IGNORECASE
from urllib.parse import quote
from io import BytesIO

from aiofiles.os import path as aiopath, remove as aioremove, makedirs
from pyrogram.handlers import CallbackQueryHandler
from pyrogram.filters import regex
from pyrogram.errors import MessageNotModified
from pyrogram.types import InputMediaPhoto
from PIL import Image
import aiohttp

from bot import bot, GK_API_URL, LOGGER, user_data
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.telegram_helper.message_utils import deleteMessage
from bot.helper.utils import request

# ── TMDB config ──────────────────────────────────────────────────────────────
# Priority:
#   1. TMDB_ACCESS_TOKEN set → Direct TMDB API with Bearer token (best)
#   2. TMDB_API_KEY set      → Direct TMDB API with api_key param
#   3. Neither set           → Cloudflare Worker (no key needed — free bypass)
TMDB_ACCESS_TOKEN = environ.get("TMDB_ACCESS_TOKEN", "").strip()
TMDB_API_KEY      = environ.get("TMDB_API_KEY", "").strip()

_TMDB_DIRECT = "https://api.themoviedb.org/3"
_TMDB_WORKER = "https://tmdbapi.the-zake.workers.dev/3"

if TMDB_ACCESS_TOKEN:
    _TMDB_BASE    = _TMDB_DIRECT
    _TMDB_HEADERS = {"Authorization": f"Bearer {TMDB_ACCESS_TOKEN}", "accept": "application/json"}
    _TMDB_KEY_PARAM = {}
    LOGGER.info("TMDB: using Direct API with Access Token (Bearer)")
elif TMDB_API_KEY:
    _TMDB_BASE    = _TMDB_DIRECT
    _TMDB_HEADERS = {"accept": "application/json"}
    _TMDB_KEY_PARAM = {"api_key": TMDB_API_KEY}
    LOGGER.info("TMDB: using Direct API with API Key")
else:
    _TMDB_BASE    = _TMDB_WORKER
    _TMDB_HEADERS = {"accept": "application/json"}
    _TMDB_KEY_PARAM = {}
    LOGGER.info("TMDB: no key/token found — using Cloudflare Worker (free bypass)")

TMDB_IMG     = "https://image.tmdb.org/t/p/"
POSTER_WAITERS = {}

_BAD_TOKENS = (
    "480p", "540p", "720p", "1080p", "2160p", "4320p", "4k", "8k",
    "hdrip", "hdcam", "camrip", "webdl", "web dl", "web-dl", "webrip",
    "bluray", "blu ray", "brrip", "dvdrip", "hdtv", "hdr", "dv", "remux",
    "x264", "x265", "h264", "h265", "hevc", "avc", "10bit", "8bit",
    "aac", "ac3", "ddp", "dd5", "atmos", "dts", "mp3", "esub", "subs", "subtitle",
    "multi", "dual", "audio", "hin", "hindi", "eng", "english", "bengali", "bangla", "urdu",
    "tamil", "telugu", "malayalam", "kannada", "marathi", "punjabi",
    "rdx", "kps", "skymovieshd", "vegamovies", "mkvcinemas", "moviesmod", "katmoviehd",
    "worldfree4u", "filmyzilla", "bollyflix", "hdhub4u", "uhd", "nf", "amzn", "dsnp", "hotstar",
)


def _normalize_spaces(text: str) -> str:
    return sub(r"\s+", " ", str(text or "")).strip(" ._-[](){}")


def _n(s: str) -> str:
    return sub(r"[^a-z0-9]+", "", str(s).lower())


def clean_movie_name(name: str) -> str:
    raw = str(name or "")
    base = ospath.basename(raw)
    base = sub(r"\.[A-Za-z0-9]{2,5}$", "", base)
    base = sub(r"[._\-\[\]\(\){}]+", " ", base)
    base = _normalize_spaces(base)

    m = search(r"(?i)\b(S\d{1,2}\s*E\d{1,3}|S\d{1,2}|Season\s*\d{1,2}|Episode\s*\d{1,3})\b", base)
    if m:
        title = _normalize_spaces(base[:m.start()])
        if title:
            return title

    ym = search(r"\b(19\d{2}|20\d{2})\b", base)
    if ym:
        before_year = _normalize_spaces(base[:ym.end()])
        if before_year:
            return before_year

    words = base.split()
    keep = []
    bad = {t.lower() for t in _BAD_TOKENS}
    for w in words:
        lw = w.lower()
        if lw in bad or lw.rstrip(".-_") in bad:
            break
        if search(r"(?i)^(proper|repack|extended|unrated|remastered|complete)$", w):
            break
        keep.append(w)
    title = _normalize_spaces(" ".join(keep))
    return title or base or raw


def _title_candidates(name: str):
    title = clean_movie_name(name)
    candidates = []

    def add(x):
        x = _normalize_spaces(x)
        if x and x.lower() not in [c.lower() for c in candidates]:
            candidates.append(x)

    add(title)
    add(sub(r"\b(19\d{2}|20\d{2})\b", "", title))
    add(sub(r"(?i)\b(Blu Ray|Bluray|WEB DL|WEBDL|WEBRip|Hindi|English|Bengali|Tamil|Telugu|ESub|x264|x265|HEVC).*", "", title))

    raw = ospath.basename(str(name or ""))
    raw = sub(r"\.[A-Za-z0-9]{2,5}$", "", raw)
    raw = sub(r"[._\-\[\]\(\){}]+", " ", raw)
    raw = _normalize_spaces(raw)
    m = search(r"(?i)\b(S\d{1,2}\s*E\d{1,3}|S\d{1,2}|Season\s*\d{1,2}|Episode\s*\d{1,3})\b", raw)
    if m:
        before = _normalize_spaces(raw[:m.start()])
        words = before.split()
        if len(words) > 2:
            add(" ".join(words[:2]))
            add(words[0])

    return candidates[:6]


def _collect_urls(data):
    urls = []
    if not isinstance(data, dict):
        return urls
    for key in ("thumb", "poster", "image", "url", "downloadUrl", "download_url"):
        val = data.get(key)
        if isinstance(val, str) and val.startswith(("http://", "https://")):
            urls.append(val)
    for key in ("thumbs", "posters", "images", "results", "data"):
        val = data.get(key)
        if isinstance(val, list):
            for item in val:
                if isinstance(item, str) and item.startswith(("http://", "https://")):
                    urls.append(item)
                elif isinstance(item, dict):
                    urls.extend(_collect_urls(item))
        elif isinstance(val, dict):
            urls.extend(_collect_urls(val))
    clean = []
    for u in urls:
        if u not in clean:
            clean.append(u)
    return clean


async def _tmdb_request(path, params=None):
    params = dict(params or {})
    params.update(_TMDB_KEY_PARAM)
    return await request(
        f"{_TMDB_BASE}{path}",
        params=params,
        headers=_TMDB_HEADERS,
    )


async def _tmdb_search(query: str):
    LOGGER.info(f"TMDB search query: {query}")

    t = query.strip()
    year = None
    m = search(r"(19|20)\d{2}$", t)
    if m:
        year = m.group(0)
        t = t[:-4].strip()

    data = await _tmdb_request("/search/multi", {
        "query": t,
        "include_adult": "false",
        "language": "en-US",
        "page": 1,
    })
    if not isinstance(data, dict):
        return None

    results = data.get("results") or []
    results = [x for x in results if x.get("media_type") in ("movie", "tv")]

    LOGGER.info(f"TMDB raw results: {len(results)}")
    if not results:
        return None

    if year:
        filtered = []
        for x in results:
            rd = x.get("release_date") or x.get("first_air_date") or ""
            if rd[:4] == year:
                filtered.append(x)
        if filtered:
            results = filtered

    nq = _n(t)
    best = None
    best_score = -1

    for x in results:
        media_type = x.get("media_type")
        title = (
            x.get("title") or x.get("name")
            or x.get("original_title") or x.get("original_name") or ""
        )
        nt = _n(title)
        rd = x.get("release_date") or x.get("first_air_date") or ""
        yr = rd[:4] if rd else ""
        vc  = x.get("vote_count", 0) or 0
        pop = x.get("popularity", 0) or 0

        sc = 0
        if len(nq) <= 3:
            if nt == nq:        sc += 1000
            elif nq in nt:      sc += 500
        else:
            if nt == nq:        sc += 4000
            elif nt.startswith(nq): sc += 2500
            elif nq in nt:      sc += 1500

        if year and yr == year:
            sc += 5000

        sc += vc * 2
        sc += pop * 10

        if sc > best_score:
            best_score = sc
            best = (media_type, x.get("id"), title, yr, x)

    if not best:
        return None

    LOGGER.info(f"TMDB selected: {best[2]} ({best[0]}, {best[3]}) score={best_score}")
    return best[4]


def _pick_image_set(items):
    en, oth, nul = [], [], []
    for x in items:
        lang = x.get("iso_639_1")
        if lang == "en":
            en.append(x)
        elif lang in (None, "", "xx"):
            nul.append(x)
        else:
            oth.append(x)
    for lst in (en, oth, nul):
        lst.sort(key=lambda z: z.get("vote_count", 0), reverse=True)
    return en or oth or nul


async def _tmdb_image_urls(item, limit=5):
    if not item:
        return []
    media_type = item.get("media_type")
    tmdb_id    = item.get("id")
    if not (media_type in ("movie", "tv") and tmdb_id):
        return []

    data = await _tmdb_request(
        f"/{media_type}/{tmdb_id}/images",
        {"include_image_language": "en,null,hi,ta,te,ml,kn,bn,mr,gu,pa,ur,fr,es,de,it,ja,ko,zh"},
    )
    if not isinstance(data, dict):
        return []

    posters_raw  = data.get("posters",   []) or []
    backdrops_raw= data.get("backdrops", []) or []

    LOGGER.info(f"TMDB images — posters: {len(posters_raw)}, backdrops: {len(backdrops_raw)}")

    urls = []

    # Posters first (portrait) — w500
    for img in _pick_image_set(posters_raw)[:limit]:
        fp = img.get("file_path")
        if fp:
            urls.append(f"{TMDB_IMG}w500{fp}")

    # Then backdrops (landscape, quality filtered) — w1280
    filtered_backs = []
    for img in backdrops_raw:
        width  = int(img.get("width") or 0)
        height = int(img.get("height") or 0)
        aspect = float(img.get("aspect_ratio") or (width / height if height else 0))
        if not img.get("file_path"):
            continue
        if width < 1000 or height < 500:
            continue
        if aspect < 1.55 or aspect > 1.90:
            continue
        filtered_backs.append(img)

    filtered_backs.sort(key=lambda p: (
        p.get("iso_639_1") not in ("en", None),
        -(p.get("vote_average") or 0),
        -(p.get("vote_count") or 0),
        -(p.get("width") or 0),
    ))

    for img in _pick_image_set(filtered_backs)[:limit]:
        fp = img.get("file_path")
        if fp:
            u = f"{TMDB_IMG}w1280{fp}"
            if u not in urls:
                urls.append(u)

    clean = []
    for u in urls:
        if u not in clean:
            clean.append(u)
    return clean[:limit]


async def fetch_tmdb_poster_urls(name, limit=5):
    for query in _title_candidates(name):
        item = await _tmdb_search(query)
        urls = await _tmdb_image_urls(item, limit)
        if urls:
            LOGGER.info(f"TMDB posters found for: {query} ({len(urls)})")
            return urls[:limit], query
    return [], clean_movie_name(name)


async def fetch_old_api_thumb_urls(name, limit=2):
    title = clean_movie_name(name)
    api   = f"{GK_API_URL}/api/thumb?name={quote(title)}"
    data  = await request(api)
    urls  = _collect_urls(data)
    return urls[:limit]


async def fetch_auto_thumb_urls(name, limit=5):
    urls, title = await fetch_tmdb_poster_urls(name, limit)
    if len(urls) < limit:
        for u in await fetch_old_api_thumb_urls(title, limit - len(urls)):
            if u not in urls:
                urls.append(u)
    if not urls:
        LOGGER.info(f"No auto thumbnail found for: {title}")
    return urls[:limit]


async def _download_valid_poster(url):
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    LOGGER.error(f"Poster download failed [{resp.status}]: {url}")
                    return None
                raw = await resp.read()
        await makedirs("Thumbnails", exist_ok=True)
        out_path = ospath.join("Thumbnails", f"auto_thumb_{int(time() * 1000)}.jpg")
        img = Image.open(BytesIO(raw)).convert("RGB")
        img.thumbnail((320, 320))
        quality = 85
        while True:
            bio = BytesIO()
            img.save(bio, "JPEG", quality=quality, optimize=True)
            if bio.tell() <= 190 * 1024 or quality <= 55:
                break
            quality -= 10
        with open(out_path, "wb") as f:
            f.write(bio.getvalue())
        return out_path if await aiopath.exists(out_path) else None
    except Exception as e:
        LOGGER.error(f"Invalid/failed auto thumbnail image: {e}")
        return None


async def download_auto_thumb(name):
    urls = await fetch_auto_thumb_urls(name, 5)
    if not urls:
        return None
    for url in urls:
        poster = await _download_valid_poster(url)
        if poster:
            return poster
    return None


async def get_auto_thumb(name):
    return await download_auto_thumb(name)


def _poster_buttons(user_id, msg_id, index, total):
    buttons = ButtonMaker()
    if total > 0:
        buttons.ibutton("⬅️ Prev", f"athumb {user_id} {msg_id} prev")
        buttons.ibutton(f"{index + 1}/{total}", f"athumb {user_id} {msg_id} noop")
        buttons.ibutton("Next ➡️", f"athumb {user_id} {msg_id} next")
        buttons.ibutton("✅ Select This", f"athumb {user_id} {msg_id} select", "footer")
        buttons.ibutton("⏭ Upload Without Poster", f"athumb {user_id} {msg_id} skip", "footer")
        return buttons.build(3, f_cols=2)
    buttons.ibutton("✅ Continue Upload", f"athumb {user_id} {msg_id} skip")
    return buttons.build(1)


async def _show_no_poster_menu(message, user_id, title):
    sent = await bot.send_message(
        chat_id=message.chat.id,
        text=(
            "⚠️ <b>Poster not available</b>\n\n"
            f"<b>Name:</b> <code>{escape(title)}</code>\n"
            "No TMDB/API poster was found. Tap Continue Upload."
        ),
        reply_to_message_id=message.id,
    )
    msg_id = sent.id
    state  = {"future": Future(), "urls": [], "index": 0, "user_id": user_id, "message": sent, "title": title}
    POSTER_WAITERS[msg_id] = state
    await sent.edit_reply_markup(reply_markup=_poster_buttons(user_id, msg_id, 0, 0))
    try:
        await wait_for(state["future"], timeout=60)
    except TimeoutError:
        pass
    finally:
        POSTER_WAITERS.pop(msg_id, None)
        try:
            await deleteMessage(sent)
        except Exception:
            pass
    return None


async def choose_auto_thumb(message, file_name, user_id):
    user_dict = user_data.get(user_id, {})
    if not user_dict.get("auto_thumbnail", False):
        return None

    title = clean_movie_name(file_name)
    urls  = await fetch_auto_thumb_urls(file_name, 5)

    if not urls:
        if user_dict.get("choose_poster", False):
            return await _show_no_poster_menu(message, user_id, title)
        return None

    if not user_dict.get("choose_poster", False):
        for url in urls:
            poster = await _download_valid_poster(url)
            if poster:
                return poster
        return None

    sent = await bot.send_photo(
        chat_id=message.chat.id,
        photo=urls[0],
        caption=(
            "🎬 <b>Choose a poster for your upload.</b>\n\n"
            f"<b>Name:</b> <code>{escape(title)}</code>\n"
            "Use Prev/Next, then tap Select This."
        ),
        reply_to_message_id=message.id,
        reply_markup=_poster_buttons(user_id, 0, 0, len(urls)),
    )
    msg_id = sent.id
    state  = {"future": Future(), "urls": urls, "index": 0, "user_id": user_id, "message": sent, "title": title}
    POSTER_WAITERS[msg_id] = state
    await sent.edit_reply_markup(reply_markup=_poster_buttons(user_id, msg_id, 0, len(urls)))

    try:
        selected = await wait_for(state["future"], timeout=180)
    except TimeoutError:
        selected = None
    finally:
        POSTER_WAITERS.pop(msg_id, None)
        try:
            await deleteMessage(sent)
        except Exception:
            pass

    if selected is None:
        return None
    poster_path = await _download_valid_poster(urls[selected])
    if poster_path:
        return poster_path
    LOGGER.error("Selected poster could not be converted to a valid image; continuing without auto poster.")
    return None


async def auto_thumb_callback(client, query):
    data = query.data.split()
    if len(data) < 4:
        return await query.answer()
    user_id = int(data[1])
    msg_id  = int(data[2])
    action  = data[3]
    if query.from_user.id != user_id:
        return await query.answer("Not yours!", show_alert=True)
    state = POSTER_WAITERS.get(msg_id)
    if not state:
        return await query.answer("This poster menu expired.", show_alert=True)
    urls = state["urls"]
    if action == "noop":
        return await query.answer()
    if action == "skip":
        if not state["future"].done():
            state["future"].set_result(None)
        return await query.answer("Continuing upload")
    if action == "select":
        if not urls:
            if not state["future"].done():
                state["future"].set_result(None)
            return await query.answer("Continuing upload")
        if not state["future"].done():
            state["future"].set_result(state["index"])
        return await query.answer("Poster selected")
    if len(urls) <= 1:
        return await query.answer("Only one poster found", show_alert=True)
    if action == "next":
        state["index"] = (state["index"] + 1) % len(urls)
    elif action == "prev":
        state["index"] = (state["index"] - 1) % len(urls)
    idx = state["index"]
    caption = (
        "🎬 <b>Choose a poster for your upload.</b>\n\n"
        f"<b>Name:</b> <code>{escape(state['title'])}</code>\n"
        "Use Prev/Next, then tap Select This."
    )
    try:
        await state["message"].edit_media(
            InputMediaPhoto(media=urls[idx], caption=caption),
            reply_markup=_poster_buttons(user_id, msg_id, idx, len(urls)),
        )
    except Exception:
        try:
            await state["message"].edit_reply_markup(reply_markup=_poster_buttons(user_id, msg_id, idx, len(urls)))
        except MessageNotModified:
            pass
    await query.answer()


bot.add_handler(CallbackQueryHandler(auto_thumb_callback, filters=regex(r"^athumb")))
