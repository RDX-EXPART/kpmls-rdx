#!/usr/bin/env python3
from asyncio import Future, TimeoutError, wait_for
from time import time
from html import escape
from os import path as ospath
from re import sub, findall
from urllib.parse import quote, urljoin
import json

from aiofiles.os import path as aiopath, remove as aioremove, makedirs
from pyrogram.handlers import CallbackQueryHandler
from pyrogram.filters import regex
from pyrogram.errors import MessageNotModified
from pyrogram.types import InputMediaPhoto
from PIL import Image

from bot import bot, GK_API_URL, LOGGER, user_data
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.telegram_helper.message_utils import deleteMessage, sendMessage
from aiohttp import ClientSession as aioClientSession
from bot.helper.utils import request

POSTER_WAITERS = {}


def _normalize_title(text: str) -> str:
    text = sub(r"[\._\-\[\]\(\)]+", " ", str(text or ""))
    text = sub(r"(?i)\b(www|com|net|org|is|in)\b", " ", text)
    text = sub(r"\s+", " ", text).strip(" -_.")
    return text


def _strip_release_noise(text: str) -> str:
    noise = (
        r"144p|240p|360p|480p|540p|720p|1080p|2160p|4320p|4k|8k|"
        r"hdrip|hdcam|camrip|cam|dvdscr|webrip|web\s?rip|web[- ]?dl|webdl|bluray|blu\s?ray|brrip|dvdrip|hdtv|"
        r"x264|x265|h264|h265|hevc|avc|10bit|8bit|aac|ac3|eac3|ddp|dd5|5\.1|7\.1|"
        r"esub|e\s?sub|subs?|subtitles?|multi|dual|audio|"
        r"hindi|hin|english|eng|bangla|bengali|ben|urdu|tamil|tam|telugu|tel|malayalam|mal|kannada|kan|"
        r"rdx|kps|skymovieshd|skymovies|vegamovies|mkvcinemas|bollyflix|moviesverse|hdhub4u|katmoviehd|"
        r"nf|netflix|amzn|amazon|hotstar|zee5|jio|sony|web|proper|repack|extended|unrated"
    )
    text = sub(rf"(?i)\b({noise})\b", " ", text)
    text = sub(r"(?i)\b(S\d{1,2}E\d{1,3}|S\d{1,2}|E\d{1,3}|Season\s*\d{1,2}|Episode\s*\d{1,3})\b", " ", text)
    text = sub(r"\s+", " ", text).strip()
    return text


def title_candidates(name: str):
    raw = ospath.basename(str(name or ""))
    raw = sub(r"\.[A-Za-z0-9]{2,5}$", "", raw)
    raw = _normalize_title(raw)
    candidates = []

    def add(v):
        v = _normalize_title(_strip_release_noise(v))
        v = sub(r"(?i)\b(is|in|com|net|org)$", "", v).strip()
        if len(v) >= 2 and v.lower() not in [x.lower() for x in candidates]:
            candidates.append(v)

    m = findall(r"(?i)^(.+?)\b(?:S\d{1,2}\s*E\d{1,3}|S\d{1,2}|Season\s*\d{1,2}|Episode\s*\d{1,3})\b", raw)
    if m:
        add(m[0])

    m = findall(r"^(.+?\b(?:19|20)\d{2})\b", raw)
    if m:
        add(m[0])
        add(sub(r"\b(19|20)\d{2}\b", " ", m[0]))

    cut = sub(r"(?i)\b(144p|240p|360p|480p|540p|720p|1080p|2160p|4k|hdrip|webrip|web[- ]?dl|bluray|blu\s?ray|brrip|dvdrip|hdtv|x264|x265|hevc|aac|ddp|esub|subs?)\b.*$", "", raw).strip()
    if cut and cut != raw:
        add(cut)

    add(raw)

    for c in list(candidates):
        no_year = sub(r"\b(19|20)\d{2}\b", " ", c)
        add(no_year)

    return candidates[:6]


def clean_movie_name(name: str) -> str:
    cands = title_candidates(name)
    return cands[0] if cands else str(name or "")


def _collect_poster_items(data):
    """Collect poster candidates from the API response.

    Supports both direct HTTP image URLs and Telegram cached poster references
    such as {chat_id, message_id}. The old code only took `thumb` URL, but the
    API can return a non-image helper URL like .../Images/7120, which causes
    PIL.UnidentifiedImageError. This keeps the full item so we can download the
    real Telegram photo when available.
    """
    items = []

    def add_item(item):
        if not item:
            return
        # Direct image URL
        if isinstance(item, str):
            if item.startswith(("http://", "https://")):
                items.append({"url": item})
            return
        if not isinstance(item, dict):
            return

        chat_id = item.get("chat_id") or item.get("chatId") or item.get("chat")
        message_id = item.get("message_id") or item.get("messageId") or item.get("msg_id")

        # Keep Telegram reference even if no URL is present.
        if chat_id and message_id:
            items.append({"chat_id": chat_id, "message_id": message_id})

        for key in ("thumb", "poster", "image", "url", "downloadUrl", "download_url"):
            val = item.get(key)
            if isinstance(val, str) and val.startswith(("http://", "https://")):
                entry = {"url": val}
                if chat_id and message_id:
                    entry.update({"chat_id": chat_id, "message_id": message_id})
                items.append(entry)

        for key in ("thumbs", "posters", "images", "results", "data"):
            val = item.get(key)
            if isinstance(val, list):
                for child in val:
                    add_item(child)
            elif isinstance(val, dict):
                add_item(val)

    add_item(data)

    # De-duplicate while preserving order.
    clean = []
    seen = set()
    for item in items:
        marker = (item.get("url"), str(item.get("chat_id")), str(item.get("message_id")))
        if marker not in seen:
            seen.add(marker)
            clean.append(item)
    return clean


async def fetch_auto_thumb_items(name, limit=8):
    for title in title_candidates(name):
        api = f"{GK_API_URL}/api/thumb?name={quote(title)}"
        try:
            data = await request(api)
        except Exception as e:
            LOGGER.error(f"Auto thumbnail API request failed for {title}: {e}")
            data = None
        items = _collect_poster_items(data)
        if items:
            LOGGER.info(f"Auto thumbnail matched title: {title}")
            return items[:limit]
        LOGGER.info(f"No auto thumbnail found for candidate: {title}")
    return []


async def fetch_auto_thumb_urls(name, limit=8):
    """Backward-compatible URL list for preview menu.

    If the API gives Telegram chat/message only, we cannot preview by URL here;
    selection still works through the item list.
    """
    items = await fetch_auto_thumb_items(name, limit)
    return [i["url"] for i in items if i.get("url")]


async def _save_as_valid_jpeg(raw_path):
    if not raw_path or not await aiopath.exists(raw_path):
        return None
    try:
        await makedirs("Thumbnails", exist_ok=True)
        out_path = ospath.join("Thumbnails", f"auto_thumb_{int(time() * 1000)}.jpg")
        with Image.open(raw_path) as img:
            img = img.convert("RGB")
            # Telegram thumbnails work best when small JPEGs.
            img.thumbnail((320, 320))
            img.save(out_path, "JPEG", quality=85, optimize=True)
        if await aiopath.exists(out_path):
            return out_path
    except Exception as e:
        LOGGER.error(f"Invalid/failed auto thumbnail image: {e}")
    return None


async def _download_url_to_temp(url, _depth=0):
    if not url or _depth > 2:
        return None
    await makedirs("Images", exist_ok=True)
    variants = [url]
    if url.startswith(GK_API_URL) and "/Images/" in url and not url.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
        variants += [f"{url}.jpg", f"{url}.jpeg", f"{url}.png", f"{url}.webp"]

    headers = {"User-Agent": "Mozilla/5.0"}
    for test_url in variants:
        raw_path = ospath.join("Images", f"auto_raw_{int(time() * 1000)}")
        try:
            async with aioClientSession(headers=headers) as session:
                async with session.get(test_url, allow_redirects=True) as response:
                    if response.status != 200:
                        continue
                    content_type = (response.headers.get("Content-Type") or "").lower()
                    data = await response.read()

            magic_ok = data[:16].startswith((b"\xff\xd8", b"\x89PNG", b"GIF8", b"RIFF", b"BM"))
            if "image" in content_type or magic_ok:
                with open(raw_path, "wb") as f:
                    f.write(data)
                return raw_path

            text = data.decode("utf-8", errors="ignore")
            nested_items = []
            try:
                nested_items = _collect_poster_items(json.loads(text))
            except Exception:
                pass
            pattern = r'''(?:src=|href=)?["']([^"']+(?:\.jpg|\.jpeg|\.png|\.webp)(?:\?[^"']*)?)["']'''
            for found in findall(pattern, text):
                nested_items.append({"url": urljoin(test_url, found)})
            for item in nested_items[:4]:
                nested_url = item.get("url") if isinstance(item, dict) else item
                if nested_url:
                    nested = await _download_url_to_temp(nested_url, _depth + 1)
                    if nested:
                        return nested

            LOGGER.error(f"Poster URL did not return an image: {content_type or 'unknown'} | {test_url}")
        except Exception as e:
            LOGGER.error(f"Poster URL download failed: {e}")
    return None


async def _download_telegram_poster(item):
    chat_id = item.get("chat_id")
    message_id = item.get("message_id")
    if not chat_id or not message_id:
        return None
    try:
        msg = await bot.get_messages(int(chat_id), int(message_id))
        if not msg:
            return None
        await makedirs("Images", exist_ok=True)
        raw_path = await bot.download_media(msg, file_name=f"Images/tg_auto_{int(time() * 1000)}")
        return raw_path
    except Exception as e:
        LOGGER.error(f"Telegram cached poster download failed: {e}")
        return None


async def _download_valid_poster(item):
    """Return a local Telegram-safe JPEG path for a poster candidate."""
    raw_path = None
    try:
        # Prefer Telegram cached message if present because API URL may be a helper URL.
        if isinstance(item, dict) and item.get("chat_id") and item.get("message_id"):
            raw_path = await _download_telegram_poster(item)
            poster = await _save_as_valid_jpeg(raw_path)
            if poster:
                return poster
            if raw_path and await aiopath.exists(raw_path):
                try:
                    await aioremove(raw_path)
                except Exception:
                    pass
                raw_path = None

        url = item.get("url") if isinstance(item, dict) else item
        if isinstance(url, str) and url.startswith(("http://", "https://")):
            raw_path = await _download_url_to_temp(url)
            return await _save_as_valid_jpeg(raw_path)
    finally:
        if raw_path and await aiopath.exists(raw_path):
            try:
                await aioremove(raw_path)
            except Exception:
                pass
    return None


async def download_auto_thumb(name):
    items = await fetch_auto_thumb_items(name, 1)
    if not items:
        return None
    return await _download_valid_poster(items[0])


async def get_auto_thumb(name):
    """Backward-compatible helper used by media_utils.py."""
    return await download_auto_thumb(name)

def _poster_buttons(user_id, msg_id, index, total):
    buttons = ButtonMaker()
    buttons.ibutton("⬅️ Prev", f"athumb {user_id} {msg_id} prev")
    buttons.ibutton(f"{index + 1}/{total}", f"athumb {user_id} {msg_id} noop")
    buttons.ibutton("Next ➡️", f"athumb {user_id} {msg_id} next")
    buttons.ibutton("✅ Select This", f"athumb {user_id} {msg_id} select", "footer")
    buttons.ibutton("🚀 Upload Without Poster", f"athumb {user_id} {msg_id} skip", "footer")
    return buttons.build(3, f_cols=2)


def _no_poster_buttons(user_id, msg_id):
    buttons = ButtonMaker()
    buttons.ibutton("✅ Done / Continue Upload", f"athumb {user_id} {msg_id} done")
    return buttons.build(1)


async def _show_no_poster_message(message, file_name, user_id):
    title = clean_movie_name(file_name)
    sent = await sendMessage(
        message,
        "⚠️ <b>Poster not available.</b>\n\n"
        f"<b>Name:</b> <code>{escape(title)}</code>\n"
        "Tap Done to continue upload without poster.",
    )
    msg_id = sent.id
    state = {"future": Future(), "urls": [], "index": 0, "user_id": user_id, "message": sent, "title": title}
    POSTER_WAITERS[msg_id] = state
    try:
        await sent.edit_reply_markup(reply_markup=_no_poster_buttons(user_id, msg_id))
    except Exception:
        pass
    try:
        await wait_for(state["future"], timeout=120)
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

    choose_poster = user_dict.get("choose_poster", False)
    items = await fetch_auto_thumb_items(file_name, 8)
    if not items:
        if choose_poster:
            return await _show_no_poster_message(message, file_name, user_id)
        return None

    if not choose_poster:
        return await _download_valid_poster(items[0])

    # Convert poster candidates before showing the menu. This guarantees that
    # preview and selected thumbnail are real JPEG files, not API helper URLs
    # like Images/7120 that PIL/Telegram cannot use as thumbnails.
    poster_paths = []
    for item in items:
        poster = await _download_valid_poster(item)
        if poster:
            poster_paths.append(poster)

    if not poster_paths:
        return await _show_no_poster_message(message, file_name, user_id)

    title = clean_movie_name(file_name)
    sent = await bot.send_photo(
        chat_id=message.chat.id,
        photo=poster_paths[0],
        caption=(
            "🎬 <b>Choose a poster for your upload.</b>\n\n"
            f"<b>Name:</b> <code>{escape(title)}</code>\n"
            "Use Prev/Next, then tap Select This."
        ),
        reply_to_message_id=message.id,
        reply_markup=_poster_buttons(user_id, 0, 0, len(poster_paths)),
    )
    msg_id = sent.id
    state = {"future": Future(), "posters": poster_paths, "index": 0, "user_id": user_id, "message": sent, "title": title}
    POSTER_WAITERS[msg_id] = state
    await sent.edit_reply_markup(reply_markup=_poster_buttons(user_id, msg_id, 0, len(poster_paths)))

    selected_index = None
    try:
        selected_index = await wait_for(state["future"], timeout=120)
    except TimeoutError:
        selected_index = None
    finally:
        POSTER_WAITERS.pop(msg_id, None)
        try:
            await deleteMessage(sent)
        except Exception:
            pass

    selected_path = None
    if selected_index is not None and 0 <= selected_index < len(poster_paths):
        selected_path = poster_paths[selected_index]

    # Delete unselected previews; keep selected_path until upload finishes.
    for idx, poster in enumerate(poster_paths):
        if poster != selected_path and await aiopath.exists(poster):
            try:
                await aioremove(poster)
            except Exception:
                pass

    return selected_path


async def auto_thumb_callback(client, query):
    data = query.data.split()
    if len(data) < 4:
        return await query.answer()
    user_id = int(data[1])
    msg_id = int(data[2])
    action = data[3]
    if query.from_user.id != user_id:
        return await query.answer("Not yours!", show_alert=True)
    state = POSTER_WAITERS.get(msg_id)
    if not state:
        return await query.answer("This poster menu expired.", show_alert=True)

    if action in ("done", "skip"):
        if not state["future"].done():
            state["future"].set_result(None)
        return await query.answer("Continuing upload")

    posters = state.get("posters", [])
    if action == "noop":
        return await query.answer()
    if action == "select":
        if not state["future"].done():
            state["future"].set_result(state["index"])
        return await query.answer("Poster selected")
    if not posters:
        return await query.answer("No poster available", show_alert=True)
    if len(posters) == 1:
        return await query.answer("Only one poster found", show_alert=True)
    if action == "next":
        state["index"] = (state["index"] + 1) % len(posters)
    elif action == "prev":
        state["index"] = (state["index"] - 1) % len(posters)
    idx = state["index"]
    caption = (
        "🎬 <b>Choose a poster for your upload.</b>\n\n"
        f"<b>Name:</b> <code>{escape(state['title'])}</code>\n"
        "Use Prev/Next, then tap Select This."
    )
    try:
        await state["message"].edit_media(
            InputMediaPhoto(media=posters[idx], caption=caption),
            reply_markup=_poster_buttons(user_id, msg_id, idx, len(posters)),
        )
    except Exception:
        try:
            await state["message"].edit_reply_markup(reply_markup=_poster_buttons(user_id, msg_id, idx, len(posters)))
        except MessageNotModified:
            pass
    await query.answer()


bot.add_handler(CallbackQueryHandler(auto_thumb_callback, filters=regex(r"^athumb")))
