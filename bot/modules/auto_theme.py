#!/usr/bin/env python3
"""
Feature: Auto Dark/Light Theme
দিন (06:00-18:00) → Light/Day style
রাত (18:00-06:00) → Dark/Night style

Fix v3:
  - Command string সরাসরি config_dict['CMD_SUFFIX'] থেকে নেওয়া হয়
    (BotCommands.AutoThemeCommand attribute না থাকলেও কাজ করবে)
  - CustomFilters.authorized ব্যবহার করা হয়েছে
"""

from asyncio import sleep
from datetime import datetime
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.filters import command, regex

from bot import bot, config_dict, LOGGER, DATABASE_URL
from bot.helper.telegram_helper.message_utils import sendMessage, editMessage, deleteMessage
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.ext_utils.db_handler import DbManger

# ─────────────────────────────────────────
#  COMMAND STRING
#  BotCommands attribute এর উপর নির্ভর না করে সরাসরি নিজে বানাই
# ─────────────────────────────────────────
_CMD_SUFFIX      = str(config_dict.get('CMD_SUFFIX', '4'))
_AUTO_THEME_CMD  = f'autotheme{_CMD_SUFFIX}'

# ─────────────────────────────────────────
#  DEFAULT CONFIG
# ─────────────────────────────────────────
AUTO_THEME_DEFAULTS = {
    'AUTO_THEME':             True,
    'AUTO_THEME_DAY_START':   '06:00',
    'AUTO_THEME_NIGHT_START': '18:00',
}

DAY_STYLE = {
    'header_icon': '☀️',
    'dl_icon':     '📥',
    'ul_icon':     '📤',
    'spd_icon':    '⚡',
    'size_icon':   '📦',
    'time_icon':   '⏱️',
    'seed_icon':   '🌱',
    'wait_icon':   '⏸️',
    'done_icon':   '✅',
    'bar_fill':    '█',
    'bar_empty':   '░',
    'theme_name':  'Day ☀️',
}

NIGHT_STYLE = {
    'header_icon': '🌙',
    'dl_icon':     '🌌',
    'ul_icon':     '🚀',
    'spd_icon':    '💫',
    'size_icon':   '🗂️',
    'time_icon':   '⏰',
    'seed_icon':   '🌑',
    'wait_icon':   '💤',
    'done_icon':   '🌟',
    'bar_fill':    '●',
    'bar_empty':   '○',
    'theme_name':  'Night 🌙',
}

_current_style: dict  = DAY_STYLE.copy()
_current_is_day: bool = True


def inject_defaults():
    for k, v in AUTO_THEME_DEFAULTS.items():
        config_dict.setdefault(k, v)


# ─────────────────────────────────────────
#  TIME HELPER
# ─────────────────────────────────────────

def _parse_hhmm(s: str) -> tuple[int, int]:
    try:
        h, m = map(int, str(s).strip().split(':'))
        return h, m
    except Exception:
        return 6, 0


def is_day_time() -> bool:
    now = datetime.now()
    cur = now.hour * 60 + now.minute
    dh, dm = _parse_hhmm(config_dict.get('AUTO_THEME_DAY_START', '06:00'))
    nh, nm = _parse_hhmm(config_dict.get('AUTO_THEME_NIGHT_START', '18:00'))
    day_start   = dh * 60 + dm
    night_start = nh * 60 + nm
    if day_start < night_start:
        return day_start <= cur < night_start
    return cur >= day_start or cur < night_start


# ─────────────────────────────────────────
#  APPLY STYLE
# ─────────────────────────────────────────

def _apply_style(is_day: bool):
    global _current_style, _current_is_day
    _current_is_day = is_day
    _current_style  = DAY_STYLE.copy() if is_day else NIGHT_STYLE.copy()
    config_dict['_ACTIVE_THEME_STYLE'] = _current_style
    LOGGER.info(f"[AutoTheme] Switched to {'Day ☀️' if is_day else 'Night 🌙'}")


# ─────────────────────────────────────────
#  BACKGROUND LOOP
# ─────────────────────────────────────────

async def auto_theme_loop():
    global _current_is_day
    LOGGER.info("[AutoTheme] Background loop started.")
    _apply_style(is_day_time())
    while True:
        await sleep(60)
        try:
            if not config_dict.get('AUTO_THEME', True):
                continue
            should_be_day = is_day_time()
            if should_be_day != _current_is_day:
                _apply_style(should_be_day)
        except Exception as e:
            LOGGER.error(f"[AutoTheme] Loop error: {e}")


# ─────────────────────────────────────────
#  PUBLIC HELPERS
# ─────────────────────────────────────────

def get_theme_icon(key: str) -> str:
    style = config_dict.get('_ACTIVE_THEME_STYLE', DAY_STYLE)
    return style.get(key, '•')


def get_theme_bar(pct: float, length: int = 12) -> str:
    style  = config_dict.get('_ACTIVE_THEME_STYLE', DAY_STYLE)
    fill   = style['bar_fill']
    empty  = style['bar_empty']
    p      = max(0.0, min(100.0, float(pct)))
    filled = int(p / 100 * length)
    return f"[{fill * filled}{empty * (length - filled)}] {int(p)}%"


# ─────────────────────────────────────────
#  MENU
# ─────────────────────────────────────────

def _status_text() -> str:
    enabled     = config_dict.get('AUTO_THEME', True)
    day_start   = config_dict.get('AUTO_THEME_DAY_START', '06:00')
    night_start = config_dict.get('AUTO_THEME_NIGHT_START', '18:00')
    current     = 'Day ☀️' if _current_is_day else 'Night 🌙'
    en_str      = '✅ Enabled' if enabled else '❌ Disabled'
    return (
        f"<b>🎨 Auto Theme Settings</b>\n\n"
        f"<b>Status:</b> {en_str}\n"
        f"<b>Current Theme:</b> {current}\n\n"
        f"<b>☀️ Day starts at:</b> {day_start}\n"
        f"<b>🌙 Night starts at:</b> {night_start}\n\n"
        f"<i>Theme switches automatically every minute.</i>"
    )


def _menu_buttons(user_id: int):
    enabled = config_dict.get('AUTO_THEME', True)
    buttons = ButtonMaker()
    toggle_label = '❌ Disable Auto Theme' if enabled else '✅ Enable Auto Theme'
    buttons.ibutton(toggle_label,              f"at {user_id} toggle")
    buttons.ibutton("☀️ Set Day Start Time",   f"at {user_id} set day")
    buttons.ibutton("🌙 Set Night Start Time", f"at {user_id} set night")
    buttons.ibutton("🔄 Force Refresh Now",    f"at {user_id} refresh")
    buttons.ibutton("❌ Close",                f"at {user_id} close")
    return buttons.build(2)


_waiting: dict = {}


# ─────────────────────────────────────────
#  HANDLERS
# ─────────────────────────────────────────

async def autotheme_command(client, message):
    user_id = message.from_user.id
    await sendMessage(message, _status_text(), _menu_buttons(user_id))


async def autotheme_callback(client, query):
    data    = query.data.split()
    user_id = int(data[1])
    action  = data[2]

    if query.from_user.id != user_id:
        return await query.answer("Not your menu!", show_alert=True)

    if action == 'close':
        await deleteMessage(query.message)
        return await query.answer()

    if action == 'toggle':
        config_dict['AUTO_THEME'] = not config_dict.get('AUTO_THEME', True)
        if DATABASE_URL:
            await DbManger().update_config({'AUTO_THEME': config_dict['AUTO_THEME']})
        toggled = 'enabled' if config_dict['AUTO_THEME'] else 'disabled'
        await editMessage(query.message, _status_text(), _menu_buttons(user_id))
        return await query.answer(f"Auto Theme {toggled}!", show_alert=True)

    if action == 'set':
        what = data[3] if len(data) > 3 else ''
        _waiting[user_id] = what
        prompts = {
            'day':   "☀️ <b>Day Mode start time পাঠান</b>\nFormat: <code>HH:MM</code> (e.g. <code>06:00</code>)",
            'night': "🌙 <b>Night Mode start time পাঠান</b>\nFormat: <code>HH:MM</code> (e.g. <code>18:00</code>)",
        }
        cancel_btn = ButtonMaker()
        cancel_btn.ibutton("❌ Cancel", f"at {user_id} back")
        await editMessage(query.message, prompts.get(what, 'Send value:'), cancel_btn.build(1))
        return await query.answer()

    if action == 'refresh':
        _apply_style(is_day_time())
        await editMessage(query.message, _status_text(), _menu_buttons(user_id))
        return await query.answer("Theme refreshed!", show_alert=True)

    if action == 'back':
        await editMessage(query.message, _status_text(), _menu_buttons(user_id))
        return await query.answer()

    await query.answer()


async def autotheme_input_handler(client, message):
    user_id = message.from_user.id
    if user_id not in _waiting:
        return
    what = _waiting.pop(user_id)
    text = message.text.strip()
    try:
        h, m = map(int, text.split(':'))
        assert 0 <= h <= 23 and 0 <= m <= 59
        value = f"{h:02d}:{m:02d}"
    except Exception:
        return await sendMessage(message, "❌ Invalid time format. Use HH:MM (e.g. 06:00)")

    if what == 'day':
        config_dict['AUTO_THEME_DAY_START'] = value
        if DATABASE_URL:
            await DbManger().update_config({'AUTO_THEME_DAY_START': value})
        await sendMessage(message, f"✅ Day Mode start time set to <b>{value}</b>")
    elif what == 'night':
        config_dict['AUTO_THEME_NIGHT_START'] = value
        if DATABASE_URL:
            await DbManger().update_config({'AUTO_THEME_NIGHT_START': value})
        await sendMessage(message, f"✅ Night Mode start time set to <b>{value}</b>")
    _apply_style(is_day_time())


# ─────────────────────────────────────────
#  REGISTER HANDLERS
#  - command string সরাসরি config থেকে নেওয়া হয়
#  - CustomFilters.authorized → owner + sudo + auth সবাই access পাবে
# ─────────────────────────────────────────

def add_handlers():
    bot.add_handler(
        MessageHandler(
            autotheme_command,
            filters=command(_AUTO_THEME_CMD) & CustomFilters.authorized,
        )
    )
    bot.add_handler(
        CallbackQueryHandler(autotheme_callback, filters=regex(r'^at '))
    )
    bot.add_handler(
        MessageHandler(autotheme_input_handler, filters=CustomFilters.authorized)
    )
    LOGGER.info(f"[AutoTheme] ✅ Handlers registered (cmd=/{_AUTO_THEME_CMD}).")
