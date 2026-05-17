#!/usr/bin/env python3
"""
Feature: Smart Bandwidth Manager
Auto detect CPU/RAM/task load → Aria2 + qBittorrent speed adjust

Fix v3:
  - Command string সরাসরি config_dict['CMD_SUFFIX'] থেকে নেওয়া হয়
    (BotCommands.BandwidthCommand attribute না থাকলেও কাজ করবে)
  - CustomFilters.authorized ব্যবহার করা হয়েছে
"""

from asyncio import sleep
from time import time
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.filters import command, regex
from psutil import cpu_percent, virtual_memory, net_io_counters

from bot import bot, config_dict, aria2, LOGGER, DATABASE_URL, download_dict
from bot.helper.telegram_helper.message_utils import sendMessage, editMessage, deleteMessage
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.ext_utils.bot_utils import get_readable_file_size
from bot.helper.ext_utils.db_handler import DbManger

# ─────────────────────────────────────────
#  COMMAND STRING
#  BotCommands attribute এর উপর নির্ভর না করে সরাসরি নিজে বানাই
# ─────────────────────────────────────────
from bot import CMD_SUFFIX as _CMD_SUFFIX
_BANDWIDTH_CMD = f'bandwidth{_CMD_SUFFIX}'

# ─────────────────────────────────────────
#  DEFAULT CONFIG
# ─────────────────────────────────────────
BW_DEFAULTS = {
    'BW_MANAGER':        True,
    'BW_CHECK_INTERVAL': 30,
    'BW_CPU_HIGH':       80,
    'BW_RAM_HIGH':       85,
    'BW_MAX_TASKS_FULL': 5,
    'BW_SPEED_FULL':     0,         # 0 = unlimited
    'BW_SPEED_MEDIUM':   52428800,  # 50 MB/s
    'BW_SPEED_LOW':      10485760,  # 10 MB/s
}

_last_net_bytes: int   = 0
_last_net_time: float  = 0.0
_current_level: str    = 'full'


def inject_defaults():
    for k, v in BW_DEFAULTS.items():
        config_dict.setdefault(k, v)


# ─────────────────────────────────────────
#  METRICS
# ─────────────────────────────────────────

def _get_metrics() -> dict:
    global _last_net_bytes, _last_net_time
    cpu   = cpu_percent(interval=1)
    ram   = virtual_memory().percent
    tasks = len(download_dict)
    net   = net_io_counters()
    now   = time()
    total = net.bytes_sent + net.bytes_recv
    elapsed   = now - _last_net_time if _last_net_time else 1
    net_speed = (total - _last_net_bytes) / elapsed if _last_net_bytes else 0
    _last_net_bytes = total
    _last_net_time  = now
    return {'cpu': cpu, 'ram': ram, 'tasks': tasks, 'net_speed': net_speed}


def _decide_level(m: dict) -> str:
    cpu_high  = config_dict.get('BW_CPU_HIGH', 80)
    ram_high  = config_dict.get('BW_RAM_HIGH', 85)
    max_tasks = config_dict.get('BW_MAX_TASKS_FULL', 5)
    if m['cpu'] >= cpu_high or m['ram'] >= ram_high or m['tasks'] >= max_tasks:
        if m['cpu'] >= cpu_high + 10 or m['ram'] >= ram_high + 10:
            return 'low'
        return 'medium'
    return 'full'


async def _apply_limit(level: str):
    global _current_level
    if level == _current_level:
        return
    speed_map = {
        'full':   config_dict.get('BW_SPEED_FULL', 0),
        'medium': config_dict.get('BW_SPEED_MEDIUM', 52428800),
        'low':    config_dict.get('BW_SPEED_LOW', 10485760),
    }
    limit     = speed_map.get(level, 0)
    limit_str = str(limit)
    LOGGER.info(f"[BandwidthMgr] {_current_level} → {level} | {get_readable_file_size(limit)}/s")
    _current_level = level

    try:
        aria2.client.change_global_option({
            'max-download-limit': limit_str,
            'max-upload-limit':   limit_str,
        })
    except Exception as e:
        LOGGER.warning(f"[BandwidthMgr] Aria2: {e}")

    try:
        from bot import get_client
        qb = get_client()
        qb.transfer_download_limit(limit)
        qb.transfer_upload_limit(limit)
    except Exception as e:
        LOGGER.warning(f"[BandwidthMgr] qBit: {e}")


# ─────────────────────────────────────────
#  BACKGROUND LOOP
# ─────────────────────────────────────────

async def bw_manager_loop():
    LOGGER.info("[BandwidthMgr] Background loop started.")
    while True:
        try:
            if config_dict.get('BW_MANAGER', True):
                m     = _get_metrics()
                level = _decide_level(m)
                await _apply_limit(level)
        except Exception as e:
            LOGGER.error(f"[BandwidthMgr] Loop error: {e}")
        await sleep(config_dict.get('BW_CHECK_INTERVAL', 30))


# ─────────────────────────────────────────
#  MENU
# ─────────────────────────────────────────

def _fmt(bps: int) -> str:
    return 'Unlimited' if bps == 0 else f"{get_readable_file_size(bps)}/s"


def _status_text() -> str:
    enabled  = config_dict.get('BW_MANAGER', True)
    en_str   = '✅ Enabled' if enabled else '❌ Disabled'
    lvl_icon = {'full': '🟢', 'medium': '🟡', 'low': '🔴'}.get(_current_level, '⚪')
    try:
        cpu = cpu_percent()
        ram = virtual_memory().percent
    except Exception:
        cpu = ram = 0.0
    return (
        f"<b>📡 Smart Bandwidth Manager</b>\n\n"
        f"<b>Status:</b> {en_str}\n"
        f"<b>Current Level:</b> {lvl_icon} {_current_level.upper()}\n\n"
        f"<b>🖥️ CPU:</b> {cpu:.1f}%  |  <b>💾 RAM:</b> {ram:.1f}%\n"
        f"<b>📋 Active Tasks:</b> {len(download_dict)}\n\n"
        f"<b>⚙️ Thresholds:</b>\n"
        f"  CPU High: {config_dict.get('BW_CPU_HIGH', 80)}%\n"
        f"  RAM High: {config_dict.get('BW_RAM_HIGH', 85)}%\n"
        f"  Max Tasks: {config_dict.get('BW_MAX_TASKS_FULL', 5)}\n\n"
        f"<b>🚦 Speed Limits:</b>\n"
        f"  🟢 Full:   {_fmt(config_dict.get('BW_SPEED_FULL', 0))}\n"
        f"  🟡 Medium: {_fmt(config_dict.get('BW_SPEED_MEDIUM', 52428800))}\n"
        f"  🔴 Low:    {_fmt(config_dict.get('BW_SPEED_LOW', 10485760))}"
    )


def _menu_buttons(user_id: int):
    enabled = config_dict.get('BW_MANAGER', True)
    buttons = ButtonMaker()
    toggle  = '❌ Disable' if enabled else '✅ Enable'
    buttons.ibutton(toggle,                   f"bw {user_id} toggle")
    buttons.ibutton("🖥️ Set CPU Threshold",   f"bw {user_id} set cpu")
    buttons.ibutton("💾 Set RAM Threshold",    f"bw {user_id} set ram")
    buttons.ibutton("📋 Set Max Tasks",        f"bw {user_id} set tasks")
    buttons.ibutton("🟡 Set Medium Speed",     f"bw {user_id} set medium")
    buttons.ibutton("🔴 Set Low Speed",        f"bw {user_id} set low")
    buttons.ibutton("🔄 Check Now",            f"bw {user_id} refresh")
    buttons.ibutton("❌ Close",                f"bw {user_id} close")
    return buttons.build(2)


_waiting: dict = {}


# ─────────────────────────────────────────
#  HANDLERS
# ─────────────────────────────────────────

async def bandwidth_command(client, message):
    await sendMessage(message, _status_text(), _menu_buttons(message.from_user.id))


async def bandwidth_callback(client, query):
    data    = query.data.split()
    user_id = int(data[1])
    action  = data[2]

    if query.from_user.id != user_id:
        return await query.answer("Not your menu!", show_alert=True)

    if action == 'close':
        await deleteMessage(query.message)
        return await query.answer()

    if action == 'toggle':
        config_dict['BW_MANAGER'] = not config_dict.get('BW_MANAGER', True)
        if DATABASE_URL:
            await DbManger().update_config({'BW_MANAGER': config_dict['BW_MANAGER']})
        toggled = 'enabled' if config_dict['BW_MANAGER'] else 'disabled'
        await editMessage(query.message, _status_text(), _menu_buttons(user_id))
        return await query.answer(f"Bandwidth Manager {toggled}!", show_alert=True)

    if action == 'refresh':
        try:
            m = _get_metrics()
            await _apply_limit(_decide_level(m))
        except Exception:
            pass
        await editMessage(query.message, _status_text(), _menu_buttons(user_id))
        return await query.answer("Checked!", show_alert=True)

    if action == 'set':
        what = data[3] if len(data) > 3 else ''
        _waiting[user_id] = what
        prompts = {
            'cpu':    "🖥️ CPU threshold % পাঠান (e.g. <code>80</code>)",
            'ram':    "💾 RAM threshold % পাঠান (e.g. <code>85</code>)",
            'tasks':  "📋 Max tasks পাঠান (e.g. <code>5</code>)",
            'medium': "🟡 Medium speed পাঠান (e.g. <code>50MB</code>)",
            'low':    "🔴 Low speed পাঠান (e.g. <code>10MB</code>)",
        }
        cancel_btn = ButtonMaker()
        cancel_btn.ibutton("❌ Cancel", f"bw {user_id} back")
        await editMessage(query.message, prompts.get(what, 'Send value:'), cancel_btn.build(1))
        return await query.answer()

    if action == 'back':
        await editMessage(query.message, _status_text(), _menu_buttons(user_id))
        return await query.answer()

    await query.answer()


def _parse_speed(text: str) -> int | None:
    text = text.strip().upper().replace(' ', '')
    try:
        if text.endswith('MB'):
            return int(float(text[:-2]) * 1024 * 1024)
        if text.endswith('KB'):
            return int(float(text[:-2]) * 1024)
        if text.endswith('GB'):
            return int(float(text[:-2]) * 1024 * 1024 * 1024)
        return int(text)
    except ValueError:
        return None


async def bandwidth_input_handler(client, message):
    user_id = message.from_user.id
    if user_id not in _waiting:
        return
    what = _waiting.pop(user_id)
    text = message.text.strip()

    if what in ('cpu', 'ram'):
        try:
            val = int(text)
            assert 1 <= val <= 99
        except Exception:
            return await sendMessage(message, "❌ 1-99 এর মধ্যে number দিন।")
        key = 'BW_CPU_HIGH' if what == 'cpu' else 'BW_RAM_HIGH'
        config_dict[key] = val
        if DATABASE_URL:
            await DbManger().update_config({key: val})
        await sendMessage(message, f"✅ {key} = <b>{val}%</b>")

    elif what == 'tasks':
        try:
            val = int(text)
            assert val >= 1
        except Exception:
            return await sendMessage(message, "❌ Positive integer দিন।")
        config_dict['BW_MAX_TASKS_FULL'] = val
        if DATABASE_URL:
            await DbManger().update_config({'BW_MAX_TASKS_FULL': val})
        await sendMessage(message, f"✅ Max tasks = <b>{val}</b>")

    elif what in ('medium', 'low'):
        bps = _parse_speed(text)
        if bps is None or bps < 0:
            return await sendMessage(message, "❌ Invalid speed। Example: <code>10MB</code>, <code>5120KB</code>")
        key = 'BW_SPEED_MEDIUM' if what == 'medium' else 'BW_SPEED_LOW'
        config_dict[key] = bps
        if DATABASE_URL:
            await DbManger().update_config({key: bps})
        await sendMessage(message, f"✅ {what.capitalize()} speed = <b>{_fmt(bps)}</b>")


# ─────────────────────────────────────────
#  REGISTER HANDLERS
#  - command string সরাসরি config থেকে নেওয়া হয়
#  - CustomFilters.authorized → owner + sudo + auth সবাই access পাবে
# ─────────────────────────────────────────

def add_handlers():
    bot.add_handler(
        MessageHandler(
            bandwidth_command,
            filters=command(_BANDWIDTH_CMD) & CustomFilters.authorized,
        )
    )
    bot.add_handler(
        CallbackQueryHandler(bandwidth_callback, filters=regex(r'^bw '))
    )
    bot.add_handler(
        MessageHandler(bandwidth_input_handler, filters=CustomFilters.authorized)
    )
    LOGGER.info(f"[BandwidthMgr] ✅ Handlers registered (cmd=/{_BANDWIDTH_CMD}).")
