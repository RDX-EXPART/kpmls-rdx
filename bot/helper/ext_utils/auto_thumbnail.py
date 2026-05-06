#!/usr/bin/env python3
from asyncio import Future, TimeoutError, wait_for
from time import time
from html import escape
from os import path as ospath
from re import sub
from urllib.parse import quote

from aiofiles.os import path as aiopath, remove as aioremove, makedirs
from pyrogram.handlers import CallbackQueryHandler
from pyrogram.filters import regex
from pyrogram.errors import MessageNotModified
from pyrogram.types import InputMediaPhoto
from PIL import Image

from bot import bot, GK_API_URL, LOGGER, user_data
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.telegram_helper.message_utils import deleteMessage, sendMessage
from bot.helper.ext_utils.bot_utils import download_image_url
from bot.helper.utils import request

POSTER_WAITERS = {}


def clean_movie_name(name: str) -> str:
    """Clean release/file names before sending them to the thumbnail API."""
    raw = str(name or "")
    clean = ospath.basename(raw)
    clean = sub(r"\.[A-Za-z0-9]{2,5}$", "", clean)
    # Remove common season/episode and dates/years/noise.
    clean = sub(r"(?i)\bS\d{1,2}\s*E\d{1,3}\b", " ", clean)
    clean = sub(r"(?i)\bSeason\s*\d{1,2}\b", " ", clean)
    clean = sub(r"(?i)\bEpisode\s*\d{1,3}\b", " ", clean)
    clean = sub(r"(?i)\bE\d{1,3}\b", " ", clean)
    clean = sub(r"\b(19|20)\d{2}\b", " ", clean)
    clean = sub(
        r"(?i)\b(144p|240p|360p|480p|540p|720p|1080p|2160p|4k|8k|hdrip|webrip|web[- ]?dl|bluray|brrip|dvdrip|hdtv|x264|x265|hevc|10bit|aac|ddp|dd5|esub|subs?|multi|dual|audio|hin|eng|bangla|bengali|hindi|urdu|tam|tel|mal|kan|rdx|kps|mkvcinemas|skymovieshd|vegamovies|bollyflix|nf|amzn|hotstar|zee5|web)\b",
        " ",
        clean,
    )
    clean = sub(r"[\._\-\[\]\(\)]+", " ", clean)
    clean = sub(r"\s+", " ", clean).strip()
    return clean or raw


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


async def fetch_auto_thumb_urls(name, limit=8):
    title = clean_movie_name(name)
    api = f"{GK_API_URL}/api/thumb?name={quote(title)}"
    try:
        data = await request(api)
    except Exception as e:
        LOGGER.error(f"Auto thumbnail API request failed: {e}")
        return []
    urls = _collect_urls(data)
    if not urls:
        LOGGER.info(f"No auto thumbnail found for: {title}")
    return urls[:limit]


async def _download_valid_poster(url):
    """Download poster URL and convert it to a valid local JPEG.

    This avoids PIL.UnidentifiedImageError and makes the selected poster Telegram-safe.
    """
    raw_path = None
    try:
        raw_path = await download_image_url(url)
        if not raw_path or not await aiopath.exists(raw_path):
            return None
        await makedirs("Thumbnails", exist_ok=True)
        out_path = ospath.join("Thumbnails", f"auto_thumb_{int(time() * 1000)}.jpg")
        with Image.open(raw_path) as img:
            img = img.convert("RGB")
            # Telegram thumbnail-safe: real JPEG, <= 320x320, under ~200KB.
            img.thumbnail((320, 320))
            quality = 85
            while quality >= 45:
                img.save(out_path, "JPEG", quality=quality, optimize=True)
                try:
                    if ospath.getsize(out_path) <= 190 * 1024:
                        break
                except Exception:
                    break
                quality -= 10
        if await aiopath.exists(out_path):
            return out_path
    except Exception as e:
        LOGGER.error(f"Invalid/failed auto thumbnail image: {e}")
    finally:
        if raw_path and await aiopath.exists(raw_path):
            try:
                await aioremove(raw_path)
            except Exception:
                pass
    return None


async def download_auto_thumb(name):
    urls = await fetch_auto_thumb_urls(name, 1)
    if not urls:
        return None
    return await _download_valid_poster(urls[0])


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
    urls = await fetch_auto_thumb_urls(file_name, 8)
    if not urls:
        if choose_poster:
            return await _show_no_poster_message(message, file_name, user_id)
        return None

    if not choose_poster:
        return await _download_valid_poster(urls[0])

    title = clean_movie_name(file_name)
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
    state = {"future": Future(), "urls": urls, "index": 0, "user_id": user_id, "message": sent, "title": title}
    POSTER_WAITERS[msg_id] = state
    await sent.edit_reply_markup(reply_markup=_poster_buttons(user_id, msg_id, 0, len(urls)))

    try:
        selected = await wait_for(state["future"], timeout=120)
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

    urls = state["urls"]
    if action == "noop":
        return await query.answer()
    if action == "select":
        if not state["future"].done():
            state["future"].set_result(state["index"])
        return await query.answer("Poster selected")
    if not urls:
        return await query.answer("No poster available", show_alert=True)
    if len(urls) == 1:
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
