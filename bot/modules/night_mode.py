#!/usr/bin/env python3
"""
Feature: Night Mode (Time-Based Speed Throttling)
Command: /nightmode — owner/sudo only, configure time-based speed limits.

How it works:
  • Owner sets a NIGHT window (e.g., 01:00 – 08:00) and a max speed limit.
  • When current time falls inside the night window:
      – Aria2 global upload/download limits are lowered.
      – qBittorrent upload/download limits are lowered.
      – A tag is shown on the /status message.
  • Outside the window: limits are restored to their normal values.
  • A background task runs every 60 s to auto-apply/remove limits.

Config stored in config_dict:
  NIGHT_MODE        True / False
  NIGHT_START       "01:00"   (24-h HH:MM, local server time)
  NIGHT_END         "06:00"
  NIGHT_SPEED_LIMIT 1048576   (bytes/s — default 1 MB/s)

The background loop is started from bot/__main__.py (see integration guide).
"""

from asyncio import sleep, create_task
from datetime import datetime
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.filters import command, regex

from bot import (
    bot, config_dict, user_data, aria2, LOGGER,
    DATABASE_URL, aria2c_global,
)
from bot.helper.telegram_helper.message_utils import sendMessage, editMessage, deleteMessage
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.ext_utils.bot_utils import get_readable_file_size
from bot.helper.ext_utils.db_handler import DbManger

# ────────────────────────────────────────────
#  DEFAULT CONFIG
#  These keys are injected into config_dict
#  on startup if not already present.
# ────────────────────────────────────────────
NIGHT_MODE_DEFAULTS = {
    'NIGHT_MODE':        False,
    'NIGHT_START':       '01:00',
    'NIGHT_END':         '06:00',
    'NIGHT_SPEED_LIMIT': 1_048_576,   # 1 MB/s in bytes
}

_night_active: bool = False   # internal state tracker


def inject_defaults():
    """Call once at startup to ensure night-mode keys exist in config_dict."""
    for k, v in NIGHT_MODE_DEFAULTS.items():
        config_dict.setdefault(k, v)


# ────────────────────────────────────────────
#  TIME HELPERS
# ────────────────────────────────────────────

def _parse_hhmm(s: str) -> tuple[int, int]:
    """Parse 'HH:MM' string, return (hour, minute). Defaults to (0, 0)."""
    try:
        h, m = map(int, s.strip().split(':'))
        return h, m
    except Exception:
        return 0, 0


def is_night_mode_active() -> bool:
    """
    Return True if current local time is inside the configured night window.
    Handles overnight ranges (e.g. 23:00 – 06:00).
    """
    if not config_dict.get('NIGHT_MODE'):
        return False

    now     = datetime.now()
    cur_min = now.hour * 60 + now.minute

    sh, sm  = _parse_hhmm(str(config_dict.get('NIGHT_START', '01:00')))
    eh, em  = _parse_hhmm(str(config_dict.get('NIGHT_END',   '08:00')))
    start   = sh * 60 + sm
    end_    = eh * 60 + em

    if start < end_:
        return start <= cur_min < end_
    else:
        # Overnight: e.g. 23:00 – 06:00
        return cur_min >= start or cur_min < end_


def get_speed_limit_bytes() -> int:
    """Return the configured night speed limit in bytes/s."""
    try:
        return int(config_dict.get('NIGHT_SPEED_LIMIT', 1_048_576))
    except (ValueError, TypeError):
        return 1_048_576


def fmt_speed(bps: int) -> str:
    return get_readable_file_size(bps) + '/s'


# ────────────────────────────────────────────
#  APPLY / REMOVE SPEED LIMITS
# ────────────────────────────────────────────

async def apply_night_limits():
    """Set reduced speed limits on Aria2 and qBittorrent."""
    limit = get_speed_limit_bytes()
    LOGGER.info(f"[NightMode] Applying limits: {fmt_speed(limit)}")

    # ── Aria2 ──
    try:
        options = {
            'max-upload-limit':   str(limit),
            'max-download-limit': str(limit),
        }
        aria2.client.change_global_option(options)
    except Exception as e:
        LOGGER.warning(f"[NightMode] Aria2 limit error: {e}")

    # ── qBittorrent ──
    try:
        from bot import get_client
        qb = get_client()
        qb.transfer_upload_limit(limit)
        qb.transfer_download_limit(limit)
    except Exception as e:
        LOGGER.warning(f"[NightMode] qBit limit error: {e}")


async def remove_night_limits():
    """Remove speed limits — restore to unlimited (0 = no limit in both tools)."""
    LOGGER.info("[NightMode] Restoring unlimited speed.")

    # ── Aria2 ──
    try:
        options = {
            'max-upload-limit':   '0',
            'max-download-limit': '0',
        }
        aria2.client.change_global_option(options)
    except Exception as e:
        LOGGER.warning(f"[NightMode] Aria2 restore error: {e}")

    # ── qBittorrent ──
    try:
        from bot import get_client
        qb = get_client()
        qb.transfer_upload_limit(0)
        qb.transfer_download_limit(0)
    except Exception as e:
        LOGGER.warning(f"[NightMode] qBit restore error: {e}")


# ────────────────────────────────────────────
#  BACKGROUND LOOP
# ────────────────────────────────────────────

async def night_mode_loop():
    """
    Background coroutine that checks every 60 s and
    applies or removes speed limits as needed.
    Start with:  create_task(night_mode_loop())   in bot/__main__.py
    """
    global _night_active
    LOGGER.info("[NightMode] Background loop started.")
    while True:
        try:
            should_be_active = is_night_mode_active()
            if should_be_active and not _night_active:
                await apply_night_limits()
                _night_active = True
            elif not should_be_active and _night_active:
                await remove_night_limits()
                _night_active = False
        except Exception as e:
            LOGGER.error(f"[NightMode] Loop error: {e}")
        await sleep(60)


# ────────────────────────────────────────────
#  STATUS HELPER (use in /status messages)
# ────────────────────────────────────────────

def night_mode_tag() -> str:
    """Returns a tag string to append to status messages, or ''."""
    if not config_dict.get('NIGHT_MODE'):
        return ''
    if is_night_mode_active():
        lim = get_speed_limit_bytes()
        return f"\n🌙 <b>Night Mode Active</b> — Max {fmt_speed(lim)}"
    return '\n☀️ <b>Night Mode</b>: scheduled'


# ────────────────────────────────────────────
#  MENU BUILDER
# ────────────────────────────────────────────

def _status_text() -> str:
    enabled = config_dict.get('NIGHT_MODE', False)
    start   = config_dict.get('NIGHT_START', '01:00')
    end_    = config_dict.get('NIGHT_END',   '08:00')
    limit   = get_speed_limit_bytes()
    active  = is_night_mode_active()

    state_icon = '🌙 Active' if active else '☀️ Inactive'
    enabled_str = '✅ Enabled' if enabled else '❌ Disabled'

    return (
        f"<b>🌙 Night Mode Settings</b>\n\n"
        f"<b>Status:</b> {enabled_str}\n"
        f"<b>Current:</b> {state_icon}\n\n"
        f"<b>⏰ Night Window:</b>  {start}  →  {end_}\n"
        f"<b>🚦 Speed Limit:</b>  {fmt_speed(limit)}\n\n"
        f"<i>Outside the window: unlimited speed\n"
        f"Inside the window: throttled to limit above</i>"
    )


def _menu_buttons(user_id: int):
    enabled = config_dict.get('NIGHT_MODE', False)
    buttons = ButtonMaker()
    toggle_label = '🌙 Disable Night Mode' if enabled else '☀️ Enable Night Mode'
    buttons.ibutton(toggle_label, f"nm {user_id} toggle")
    buttons.ibutton("⏰ Set Start Time", f"nm {user_id} set start")
    buttons.ibutton("⏰ Set End Time",   f"nm {user_id} set end")
    buttons.ibutton("🚦 Set Speed Limit",  f"nm {user_id} set speed")
    if is_night_mode_active():
        buttons.ibutton("⚡ Force Remove Limits Now", f"nm {user_id} forceday")
    buttons.ibutton("❌ Close", f"nm {user_id} close")
    return buttons.build(2)


# ────────────────────────────────────────────
#  WAITING FOR INPUT STATE
# ────────────────────────────────────────────
_waiting: dict = {}   # user_id → what we're waiting for


# ────────────────────────────────────────────
#  COMMAND HANDLER
# ────────────────────────────────────────────

async def nightmode_command(client, message):
    user_id = message.from_user.id
    await sendMessage(message, _status_text(), _menu_buttons(user_id))


# ────────────────────────────────────────────
#  CALLBACK HANDLER
# ────────────────────────────────────────────

async def nightmode_callback(client, query):
    data    = query.data.split()
    user_id = int(data[1])
    action  = data[2]

    if query.from_user.id != user_id:
        return await query.answer("Not your menu!", show_alert=True)

    if action == 'close':
        await deleteMessage(query.message)
        return await query.answer()

    if action == 'toggle':
        config_dict['NIGHT_MODE'] = not config_dict.get('NIGHT_MODE', False)
        if DATABASE_URL:
            await DbManger().update_config({'NIGHT_MODE': config_dict['NIGHT_MODE']})
        if config_dict['NIGHT_MODE'] and is_night_mode_active():
            await apply_night_limits()
        elif not config_dict['NIGHT_MODE']:
            await remove_night_limits()
        await editMessage(query.message, _status_text(), _menu_buttons(user_id))
        toggled = 'enabled' if config_dict['NIGHT_MODE'] else 'disabled'
        return await query.answer(f"Night Mode {toggled}!", show_alert=True)

    if action == 'set':
        what = data[3] if len(data) > 3 else ''
        _waiting[user_id] = what
        prompts = {
            'start': (
                "⏰ <b>Send new Night Mode start time</b>\n"
                "Format: <code>HH:MM</code>  (24-hour)\n"
                "Example: <code>01:00</code>"
            ),
            'end': (
                "⏰ <b>Send new Night Mode end time</b>\n"
                "Format: <code>HH:MM</code>  (24-hour)\n"
                "Example: <code>08:00</code>"
            ),
            'speed': (
                "🚦 <b>Send speed limit</b>\n"
                "Examples: <code>512KB</code>  <code>1MB</code>  <code>2MB</code>\n"
                "(KB and MB suffixes accepted)"
            ),
        }
        await editMessage(
            query.message,
            prompts.get(what, 'Send value:'),
            ButtonMaker().build(0),
        )
        return await query.answer()

    if action == 'forceday':
        global _night_active
        await remove_night_limits()
        _night_active = False
        await editMessage(query.message, _status_text(), _menu_buttons(user_id))
        return await query.answer("Limits removed!", show_alert=True)

    await query.answer()


# ────────────────────────────────────────────
#  INPUT HANDLER (receives text after "set" prompt)
# ────────────────────────────────────────────

def _parse_speed_input(text: str) -> int | None:
    """Parse user-entered speed like '1MB', '512KB', '2097152'."""
    text = text.strip().upper().replace(' ', '')
    try:
        if text.endswith('MB'):
            return int(float(text[:-2]) * 1024 * 1024)
        if text.endswith('KB'):
            return int(float(text[:-2]) * 1024)
        return int(text)
    except ValueError:
        return None


async def nightmode_input_handler(client, message):
    user_id = message.from_user.id
    if user_id not in _waiting:
        return

    what  = _waiting.pop(user_id)
    text  = message.text.strip()

    if what in ('start', 'end'):
        # Validate HH:MM
        try:
            h, m = map(int, text.split(':'))
            assert 0 <= h <= 23 and 0 <= m <= 59
            value = f"{h:02d}:{m:02d}"
        except Exception:
            return await sendMessage(message, "❌ Invalid time format. Use HH:MM (e.g. 01:00)")

        key = 'NIGHT_START' if what == 'start' else 'NIGHT_END'
        config_dict[key] = value
        if DATABASE_URL:
            await DbManger().update_config({key: value})
        label = 'start' if what == 'start' else 'end'
        await sendMessage(message, f"✅ Night Mode {label} time set to <b>{value}</b>")

    elif what == 'speed':
        bps = _parse_speed_input(text)
        if bps is None or bps <= 0:
            return await sendMessage(
                message,
                "❌ Invalid speed. Use formats like: <code>1MB</code>, <code>512KB</code>",
            )
        config_dict['NIGHT_SPEED_LIMIT'] = bps
        if DATABASE_URL:
            await DbManger().update_config({'NIGHT_SPEED_LIMIT': bps})
        await sendMessage(message, f"✅ Night Mode speed limit set to <b>{fmt_speed(bps)}</b>")


# ────────────────────────────────────────────
#  REGISTER HANDLERS
# ────────────────────────────────────────────

def add_handlers():
    bot.add_handler(
        MessageHandler(
            nightmode_command,
            filters=command(BotCommands.NightModeCommand) & CustomFilters.owner,
        )
    )
    bot.add_handler(
        CallbackQueryHandler(nightmode_callback, filters=regex(r'^nm '))
    )
    bot.add_handler(
        MessageHandler(
            nightmode_input_handler,
            filters=CustomFilters.owner,
        )
    )
