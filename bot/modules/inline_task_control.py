#!/usr/bin/env python3
"""
Feature: Inline Control Buttons — Pause / Resume / Cancel / Retry
Status message এ প্রতিটা task এর জন্য বাটন।

Fix v3:
  - is_pausable() → শুধু status string check করে, method probe করে না
  - Pause action → aria2.client.pause(gid) সরাসরি ব্যবহার করে
  - Upload/Seed/QueueUp/Extract/Compress → Pause বাটন দেখায় না
"""

from asyncio import sleep
from pyrogram.handlers import CallbackQueryHandler
from pyrogram.filters import regex

from bot import (
    bot, download_dict, download_dict_lock,
    OWNER_ID, user_data, LOGGER, config_dict, aria2
)
from bot.helper.ext_utils.bot_utils import getDownloadByGid, new_task
from bot.helper.telegram_helper.message_utils import sendMessage, auto_delete_message

# ─────────────────────────────────────────
#  RETRY STORE — gid → original command info
# ─────────────────────────────────────────
_retry_store: dict = {}


def register_retry(gid: str, chat_id: int, user_id: int, command_text: str):
    _retry_store[gid] = {
        'chat_id':      chat_id,
        'user_id':      user_id,
        'command_text': command_text,
    }


def unregister_retry(gid: str):
    _retry_store.pop(gid, None)


# ─────────────────────────────────────────
#  STATUS-BASED PAUSABLE CHECK
#  Upload / Seed / QueueUp / Extract / Compress → pause করা যাবে না
# ─────────────────────────────────────────
_UNPAUSABLE_STATUSES = {
    "Upload", "Seed", "QueueUp", "Extract",
    "Compress", "SeedWait", "UpWait",
}


def is_pausable(download) -> bool:
    """Return True if the task is in a phase that supports pausing."""
    try:
        tstatus = str(download.status())
        return tstatus not in _UNPAUSABLE_STATUSES
    except Exception:
        return False


# ─────────────────────────────────────────
#  PERMISSION CHECK
# ─────────────────────────────────────────

def _can_control(query_user_id: int, task_user_id: int) -> bool:
    if query_user_id == OWNER_ID:
        return True
    if query_user_id == task_user_id:
        return True
    if user_data.get(query_user_id, {}).get('is_sudo'):
        return True
    return False


# ─────────────────────────────────────────
#  ARIA2 / QBITTORRENT PAUSE HELPER
# ─────────────────────────────────────────

async def _do_pause(dl, gid: str) -> bool:
    """Try to pause via Aria2 first, then qBittorrent, then object method."""
    # 1) Aria2
    try:
        aria2.client.pause(gid)
        return True
    except Exception as e:
        LOGGER.debug(f"[InlineCtrl] Aria2 pause failed: {e}")

    # 2) qBittorrent
    try:
        from bot import get_client as _qb_get
        qb = _qb_get()
        qb.torrents_pause(torrent_hashes=gid)
        return True
    except Exception as e:
        LOGGER.debug(f"[InlineCtrl] qBit pause failed: {e}")

    # 3) Object-level fallback
    try:
        obj = dl.download()
        if hasattr(obj, 'pause'):
            await obj.pause()
            return True
    except Exception as e:
        LOGGER.debug(f"[InlineCtrl] Object pause failed: {e}")

    return False


async def _do_resume(dl, gid: str) -> bool:
    """Try to resume via Aria2 first, then qBittorrent, then object method."""
    try:
        aria2.client.unpause(gid)
        return True
    except Exception as e:
        LOGGER.debug(f"[InlineCtrl] Aria2 unpause failed: {e}")

    try:
        from bot import get_client as _qb_get
        qb = _qb_get()
        qb.torrents_resume(torrent_hashes=gid)
        return True
    except Exception as e:
        LOGGER.debug(f"[InlineCtrl] qBit resume failed: {e}")

    try:
        obj = dl.download()
        if hasattr(obj, 'resume'):
            await obj.resume()
            return True
    except Exception as e:
        LOGGER.debug(f"[InlineCtrl] Object resume failed: {e}")

    return False


# ─────────────────────────────────────────
#  CALLBACK HANDLER
# ─────────────────────────────────────────

@new_task
async def inline_task_callback(client, query):
    data = query.data.split()
    # format: itc <action> <gid> <task_user_id>
    if len(data) < 4:
        return await query.answer("Invalid data.", show_alert=True)

    action       = data[1]
    gid          = data[2]
    task_user_id = int(data[3])
    caller_id    = query.from_user.id

    if not _can_control(caller_id, task_user_id):
        return await query.answer("⛔ এটা আপনার task নয়!", show_alert=True)

    dl = await getDownloadByGid(gid)

    # ── PAUSE ──────────────────────────────
    if action == 'pause':
        if dl is None:
            return await query.answer("Task পাওয়া যায়নি বা শেষ হয়ে গেছে।", show_alert=True)
        if not is_pausable(dl):
            tstatus = str(dl.status())
            return await query.answer(
                f"⚠️ '{tstatus}' phase এ pause করা যায় না।\nDownload চলাকালীনই pause সম্ভব।",
                show_alert=True,
            )
        ok = await _do_pause(dl, gid)
        if ok:
            await query.answer("⏸ Task pause করা হয়েছে!", show_alert=True)
            LOGGER.info(f"[InlineCtrl] Paused GID={gid} by user={caller_id}")
        else:
            await query.answer("❌ Pause সম্ভব হয়নি। Manually cancel করুন।", show_alert=True)

    # ── RESUME ─────────────────────────────
    elif action == 'resume':
        if dl is None:
            return await query.answer("Task পাওয়া যায়নি।", show_alert=True)
        ok = await _do_resume(dl, gid)
        if ok:
            await query.answer("▶ Task resume করা হয়েছে!", show_alert=True)
            LOGGER.info(f"[InlineCtrl] Resumed GID={gid} by user={caller_id}")
        else:
            await query.answer("Resume সম্ভব হয়নি।", show_alert=True)

    # ── CANCEL ─────────────────────────────
    elif action == 'cancel':
        if dl is None:
            return await query.answer("Task আগেই শেষ হয়ে গেছে।", show_alert=True)
        try:
            obj = dl.download()
            await obj.cancel_download()
            await query.answer("❌ Task cancel করা হয়েছে!", show_alert=True)
            LOGGER.info(f"[InlineCtrl] Cancelled GID={gid} by user={caller_id}")
        except Exception as e:
            LOGGER.error(f"[InlineCtrl] Cancel error: {e}")
            await query.answer(f"Error: {e}", show_alert=True)

    # ── RETRY ──────────────────────────────
    elif action == 'retry':
        info = _retry_store.get(gid)
        if not info:
            return await query.answer(
                "Retry info নেই। Original command আবার পাঠান।",
                show_alert=True,
            )
        try:
            if dl is not None:
                try:
                    obj = dl.download()
                    await obj.cancel_download()
                    await sleep(2)
                except Exception:
                    pass
            await bot.send_message(
                chat_id=info['chat_id'],
                text=info['command_text'],
                disable_web_page_preview=True,
            )
            await query.answer("🔄 Retry শুরু হয়েছে!", show_alert=True)
            LOGGER.info(f"[InlineCtrl] Retry GID={gid} by user={caller_id}")
        except Exception as e:
            LOGGER.error(f"[InlineCtrl] Retry error: {e}")
            await query.answer(f"Retry failed: {e}", show_alert=True)

    else:
        await query.answer("Unknown action.", show_alert=True)


# ─────────────────────────────────────────
#  REGISTER HANDLERS
# ─────────────────────────────────────────

def add_handlers():
    bot.add_handler(
        CallbackQueryHandler(inline_task_callback, filters=regex(r'^itc '))
    )
    LOGGER.info("[InlineCtrl] ✅ Inline task control handler registered.")
