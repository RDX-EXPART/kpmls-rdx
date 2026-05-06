#!/usr/bin/env python3
from asyncio import Future, TimeoutError, wait_for
from time import time
from html import escape
from os import path as ospath, getsize
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
from bot.helper.telegram_helper.message_utils import deleteMessage
from bot.helper.ext_utils.bot_utils import download_image_url
from bot.helper.utils import request

POSTER_WAITERS = {}


def clean_movie_name(name: str) -> str:
    raw = str(name or "")
    clean = ospath.basename(raw)
    clean = sub(r"\.[A-Za-z0-9]{2,5}$", "", clean)
    clean = sub(r"(?i)\b(480p|720p|1080p|2160p|4k|8k|hdrip|webrip|web[- ]?dl|bluray|brrip|dvdrip|x264|x265|hevc|10bit|aac|ddp|esub|multi|hin|eng|bangla|bengali|hindi|urdu|rdx|kps|mkvcinemas|skymovieshd|nf|amzn|web)\b", " ", clean)
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
    data = await request(api)
    urls = _collect_urls(data)
    if not urls:
        LOGGER.info(f"No auto thumbnail found for: {title}")
    return urls[:limit]


async def normalize_telegram_thumb(image_path):
    """Convert any image to a Telegram-safe JPEG thumbnail.

    Telegram thumbnails should be small JPEG files. Keeping the selected
    poster full-size can upload successfully but still show no thumbnail.
    This makes the file valid, under ~200 KB, and max 320x320.
    """
    if not image_path or not await aiopath.exists(image_path):
        return None
    await makedirs("Thumbnails", exist_ok=True)
    out_path = ospath.join("Thumbnails", f"tg_thumb_{int(time() * 1000)}.jpg")
    try:
        with Image.open(image_path) as img:
            if img.format == "JPEG" and max(img.size) <= 320 and getsize(image_path) <= 200 * 1024:
                return image_path
            img = img.convert("RGB")
            img.thumbnail((320, 320))
            quality = 85
            while quality >= 45:
                img.save(out_path, "JPEG", quality=quality, optimize=True)
                if getsize(out_path) <= 200 * 1024:
                    break
                quality -= 10
        if await aiopath.exists(out_path):
            return out_path
    except Exception as e:
        LOGGER.error(f"Invalid thumbnail image skipped: {image_path} | {e}")
    try:
        if await aiopath.exists(out_path):
            await aioremove(out_path)
    except Exception:
        pass
    return None


async def _download_valid_poster(url):
    """Download poster URL and convert it to a valid Telegram thumbnail."""
    raw_path = None
    thumb_path = None
    try:
        raw_path = await download_image_url(url)
        if not raw_path or not await aiopath.exists(raw_path):
            return None
        thumb_path = await normalize_telegram_thumb(raw_path)
        return thumb_path
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
    """Backward-compatible helper used by media_utils.py.
    Returns a local thumbnail file path from the auto thumbnail API, or None.
    """
    return await download_auto_thumb(name)


def _poster_buttons(user_id, msg_id, index, total):
    buttons = ButtonMaker()
    buttons.ibutton("⬅️ Prev", f"athumb {user_id} {msg_id} prev")
    buttons.ibutton(f"{index + 1}/{total}", f"athumb {user_id} {msg_id} noop")
    buttons.ibutton("Next ➡️", f"athumb {user_id} {msg_id} next")
    buttons.ibutton("✅ Select This", f"athumb {user_id} {msg_id} select", "footer")
    buttons.ibutton("❌ Cancel", f"athumb {user_id} {msg_id} skip", "footer")
    return buttons.build(3, f_cols=2)



def _no_poster_buttons(user_id, msg_id):
    buttons = ButtonMaker()
    buttons.ibutton("✅ Done / Start Upload", f"athumb {user_id} {msg_id} done")
    return buttons.build(1)


async def _show_no_poster_menu(message, title, user_id):
    sent = await bot.send_message(
        chat_id=message.chat.id,
        text=(
            "🖼️ <b>Poster not available</b>\n\n"
            f"<b>Name:</b> <code>{escape(title)}</code>\n"
            "API did not find a poster for this file.\n\n"
            "Tap Done to continue upload without poster."
        ),
        reply_to_message_id=message.id,
        reply_markup=_no_poster_buttons(user_id, 0),
    )
    msg_id = sent.id
    state = {"future": Future(), "urls": [], "index": 0, "user_id": user_id, "message": sent, "title": title, "no_poster": True}
    POSTER_WAITERS[msg_id] = state
    await sent.edit_reply_markup(reply_markup=_no_poster_buttons(user_id, msg_id))
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

    urls = await fetch_auto_thumb_urls(file_name, 8)
    title = clean_movie_name(file_name)
    choose_poster = user_dict.get("choose_poster", False)
    if not urls:
        if choose_poster:
            return await _show_no_poster_menu(message, title, user_id)
        return None

    if not choose_poster:
        return await download_auto_thumb(file_name)

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
    urls = state["urls"]
    if action in ("noop", "done"):
        if action == "done" and not state["future"].done():
            state["future"].set_result(None)
            return await query.answer("Continuing upload")
        return await query.answer()
    if state.get("no_poster"):
        return await query.answer("Poster not available. Tap Done.", show_alert=True)
    if action == "skip":
        if not state["future"].done():
            state["future"].set_result(None)
        return await query.answer("Skipped")
    if action == "select":
        if not state["future"].done():
            state["future"].set_result(state["index"])
        return await query.answer("Poster selected")
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
