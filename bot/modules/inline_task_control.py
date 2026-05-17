#!/usr/bin/env python3
"""
Feature: Inline Control Buttons — Pause / Resume / Cancel / Retry
প্রতিটা task এর নিচে buttons আসবে।
Button callback format: itc_<action>_<gid>

Integration in bot/__main__.py:
    from bot.modules import inline_task_control
    inline_task_control.add_handlers()

Usage in get_readable_message() (bot_utils.py):
    from bot.modules.inline_task_control import build_task_buttons
    button = build_task_buttons(download.gid(), download.message.from_user.id)
"""

from asyncio import sleep
from pyrogram.handlers import CallbackQueryHandler
from pyrogram.filters import regex

from bot import (
    bot, download_dict, download_dict_lock,
    OWNER_ID, user_data, LOGGER, config_dict
)
from bot.helper.ext_utils.bot_utils import getDownloadByGid, MirrorStatus, new_task
from bot.helper.telegram_helper.message_utils import sendMessage, auto_delete_message
from bot.helper.telegram_helper.button_build import ButtonMaker

# ─────────────────────────────────────────
#  RETRY STORE  —  gid → original message text + chat_id
# ─────────────────────────────────────────
_retry_store: dict[str, dict] = {}


def register_retry(gid: str, chat_id: int, user_id: int, command_text: str):
    """Call this when a task starts so Retry can re-issue the command."""
    _retry_store[gid] = {
        'chat_id':      chat_id,
        'user_id':      user_id,
        'command_text': command_text,
    }


def unregister_retry(gid: str):
    _retry_store.pop(gid, None)


# ─────────────────────────────────────────
#  BUTTON BUILDER  —  call from status message code
# ─────────────────────────────────────────

def build_task_buttons(gid: str, user_id: int):
    """
    Returns a ButtonMaker markup with Pause/Resume/Cancel/Retry.
    Embed in the per-task status message.
    """
    buttons = ButtonMaker()
    buttons.ibutton("⏸ Pause",   f"itc pause {gid} {user_id}")
    buttons.ibutton("▶ Resume",  f"itc resume {gid} {user_id}")
    buttons.ibutton("❌ Cancel",  f"itc cancel {gid} {user_id}")
    buttons.ibutton("🔄 Retry",  f"itc retry {gid} {user_id}")
    return buttons.build(4)


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
#  CALLBACK HANDLER
# ─────────────────────────────────────────

@new_task
async def inline_task_callback(client, query):
    data        = query.data.split()
    # format: itc <action> <gid> <task_user_id>
    if len(data) < 4:
        return await query.answer("Invalid data.", show_alert=True)

    action       = data[1]
    gid          = data[2]
    task_user_id = int(data[3])
    caller_id    = query.from_user.id

    if not _can_control(caller_id, task_user_id):
        return await query.answer("⛔ This task is not yours!", show_alert=True)

    dl = await getDownloadByGid(gid)

    # ── PAUSE ──────────────────────────────
    if action == 'pause':
        if dl is None:
            return await query.answer("Task not found or already finished.", show_alert=True)
        status = str(dl.status())
        if status == MirrorStatus.STATUS_PAUSED:
            return await query.answer("Already paused.", show_alert=True)
        try:
            obj = dl.download()
            # Aria2
            if hasattr(obj, 'pause'):
                await obj.pause()
            # qBittorrent
            elif hasattr(obj, 'client') and hasattr(obj.client, 'torrents_pause'):
                obj.client.torrents_pause(torrent_hashes=gid)
            else:
                return await query.answer("Pause not supported for this task type.", show_alert=True)
            await query.answer("⏸ Task paused!", show_alert=True)
            LOGGER.info(f"[InlineCtrl] Paused GID={gid} by user={caller_id}")
        except Exception as e:
            LOGGER.error(f"[InlineCtrl] Pause error: {e}")
            await query.answer(f"Error: {e}", show_alert=True)

    # ── RESUME ─────────────────────────────
    elif action == 'resume':
        if dl is None:
            return await query.answer("Task not found.", show_alert=True)
        try:
            obj = dl.download()
            if hasattr(obj, 'resume'):
                await obj.resume()
            elif hasattr(obj, 'client') and hasattr(obj.client, 'torrents_resume'):
                obj.client.torrents_resume(torrent_hashes=gid)
            else:
                return await query.answer("Resume not supported for this task type.", show_alert=True)
            await query.answer("▶ Task resumed!", show_alert=True)
            LOGGER.info(f"[InlineCtrl] Resumed GID={gid} by user={caller_id}")
        except Exception as e:
            LOGGER.error(f"[InlineCtrl] Resume error: {e}")
            await query.answer(f"Error: {e}", show_alert=True)

    # ── CANCEL ─────────────────────────────
    elif action == 'cancel':
        if dl is None:
            return await query.answer("Task already finished or not found.", show_alert=True)
        try:
            obj = dl.download()
            await obj.cancel_download()
            await query.answer("❌ Task cancelled!", show_alert=True)
            LOGGER.info(f"[InlineCtrl] Cancelled GID={gid} by user={caller_id}")
        except Exception as e:
            LOGGER.error(f"[InlineCtrl] Cancel error: {e}")
            await query.answer(f"Error: {e}", show_alert=True)

    # ── RETRY ──────────────────────────────
    elif action == 'retry':
        info = _retry_store.get(gid)
        if not info:
            return await query.answer(
                "Cannot retry — original task info not saved.\n"
                "Please re-send the original command manually.",
                show_alert=True
            )
        try:
            # Cancel running task first if still alive
            if dl is not None:
                try:
                    obj = dl.download()
                    await obj.cancel_download()
                    await sleep(2)
                except Exception:
                    pass

            # Re-send the original command to the same chat
            await bot.send_message(
                chat_id=info['chat_id'],
                text=info['command_text'],
                disable_web_page_preview=True,
            )
            await query.answer("🔄 Retry triggered!", show_alert=True)
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
    LOGGER.info("[InlineCtrl] Inline task control buttons registered.")
