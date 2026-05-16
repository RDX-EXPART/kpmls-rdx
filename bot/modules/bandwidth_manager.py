#!/usr/bin/env python3
"""
Feature: Smart Bandwidth Manager
Auto detect:
  - Server CPU/RAM load
  - Active task count
  - Network I/O speed
তারপর Aria2 + qBittorrent এর speed dynamically adjust করে।

Commands:
  /bandwidth  — owner/sudo only

Integration in bot/__main__.py:
    from bot.modules import bandwidth_manager
    from bot.modules.bandwidth_manager import bw_manager_loop, inject_defaults as bw_inject
    bw_inject()
    create_task(bw_manager_loop())
    bandwidth_manager.add_handlers()
"""

from asyncio import sleep
from time import time
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.filters import command, regex
from psutil import cpu_percent, virtual_memory, net_io_counters, disk_usage

from bot import bot, config_dict, aria2, LOGGER, DATABASE_URL, download_dict
from bot.helper.telegram_helper.message_utils import sendMessage, editMessage, deleteMessage
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.ext_utils.bot_utils import get_readable_file_size
from bot.helper.ext_utils.db_handler import DbManger

# ─────────────────────────────────────────
#  DEFAULT CONFIG
# ─────────────────────────────────────────
BW_DEFAULTS = {
    'BW_MANAGER':            True,
    'BW_CHECK_INTERVAL':     30,       # seconds between checks
    'BW_CPU_HIGH':           80,       # CPU% threshold — reduce speed
    'BW_RAM_HIGH':           85,       # RAM% threshold — reduce speed
    'BW_MAX_TASKS_FULL':     5,        # active tasks before throttling
    'BW_SPEED_FULL':         0,        # 0 = unlimited (bytes/s)
    'BW_SPEED_MEDIUM':       52428800, # 50 MB/s
    'BW_SPEED_LOW':          10485760, # 10 MB/s
}

# ─────────────────────────────────────────
#  INTERNAL STATE
# ─────────────────────────────────────────
_last_net_bytes: int = 0
_last_net_time: float = 0.0
_current_level: str = 'full'   # 'full' | 'medium' | 'low'


def inject_defaults():
    for k, v in BW_DEFAULTS.items():
        config_dict.setdefault(k, v)


# ─────────────────────────────────────────
#  METRICS
# ─────────────────────────────────────────

def _get_metrics() -> dict:
    global _last_net_bytes, _last_net_time

    cpu  = cpu_percent(interval=1)
    ram  = virtual_memory().percent
    tasks = len(download_dict)

    net  = net_io_counters()
    now  = time()
    total_bytes = net.bytes_sent + net.bytes_recv
    elapsed     = now - _last_net_time if _last_net_time else 1
    net_speed   = (total_bytes - _last_net_bytes) / elapsed if _last_net_bytes else 0
    _last_net_bytes = total_bytes
    _last_net_time  = now

    return {
        'cpu':       cpu,
        'ram':       ram,
        'tasks':     tasks,
        'net_speed': net_speed,
    }


# ─────────────────────────────────────────
#  DECISION LOGIC
# ─────────────────────────────────────────

def _decide_level(m: dict) -> str:
    cpu_high  = config_dict.get('BW_CPU_HIGH', 80)
    ram_high  = config_dict.get('BW_RAM_HIGH', 85)
    max_tasks = config_dict.get('BW_MAX_TASKS_FULL', 5)

    if m['cpu'] >= cpu_high or m['ram'] >= ram_high or m['tasks'] >= max_tasks:
        # heavy load → low speed
        if m['cpu'] >= cpu_high + 10 or m['ram'] >= ram_high + 10:
            return 'low'
        return 'medium'
    return 'full'


# ─────────────────────────────────────────
#  APPLY LIMITS
# ─────────────────────────────────────────

async def _apply_limit(level: str):
    global _current_level
    if level == _current_level:
        return

    speed_map = {
        'full':   config_dict.get('BW_SPEED_FULL', 0),
        'medium': config_dict.get('BW_SPEED_MEDIUM', 52428800),
        'low':    config_dict.get('BW_SPEED_LOW', 10485760),
    }
    limit = speed_map.get(level, 0)
    limit_str = str(limit)

    LOGGER.info(f"[BandwidthMgr] Level: {_current_level} → {level} | Limit: {get_readable_file_size(limit)}/s")
    _current_level = level

    # ── Aria2 ──
    try:
        aria2.client.change_global_option({
            'max-download-limit': limit_str,
            'max-upload-limit':   limit_str,
        })
    except Exception as e:
        LOGGER.warning(f"[BandwidthMgr] Aria2 error: {e}")

    # ── qBittorrent ──
    try:
        from bot import get_client
        qb = get_client()
        qb.transfer_download_limit(limit)
        qb.transfer_upload_limit(limit)
    except Exception as e:
        LOGGER.warning(f"[BandwidthMgr] qBit error: {e}")


# ─────────────────────────────────────────
#  BACKGROUND LOOP
# ─────────────────────────────────────────

async def bw_manager_loop():
    LOGGER.info("[BandwidthMgr] Background loop started.")
    while True:
        try:
            if config_dict.get('BW_MANAGER', True):
                m = _get_metrics()
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
        cpu = ram = 0

    return (
        f"<b>📡 Smart Bandwidth Manager</b>\n\n"
        f"<b>Status:</b> {en_str}\n"
        f"<b>Current Level:</b> {lvl_icon} {_current_level.upper()}\n\n"
        f"<b>🖥️ CPU:</b> {cpu:.1f}%  |  <b>💾 RAM:</b> {ram:.1f}%\n"
        f"<b>📋 Active Tasks:</b> {len(download_dict)}\n\n"
        f"<b>⚙️ Thresholds:</b>\n"
        f"  CPU High: {config_dict.get('BW_CPU_HIGH', 80)}%\n"
        f"  RAM High: {config_dict.get('BW_RAM_HIGH', 85)}%\n"
        f"  Max Tasks (Full): {config_dict.get('BW_MAX_TASKS_FULL', 5)}\n\n"
        f"<b>🚦 Speed Limits:</b>\n"
        f"  🟢 Full:   {_fmt(config_dict.get('BW_SPEED_FULL', 0))}\n"
        f"  🟡 Medium: {_fmt(config_dict.get('BW_SPEED_MEDIUM', 52428800))}\n"
        f"  🔴 Low:    {_fmt(config_dict.get('BW_SPEED_LOW', 10485760))}"
    )


def _menu_buttons(user_id: int):
    enabled = config_dict.get('BW_MANAGER', True)
    buttons = ButtonMaker()
    toggle  = '❌ Disable' if enabled else '✅ Enable'
    buttons.ibutton(toggle,                        f"bw {user_id} toggle")
    buttons.ibutton("🖥️ Set CPU Threshold",         f"bw {user_id} set cpu")
    buttons.ibutton("💾 Set RAM Threshold",         f"bw {user_id} set ram")
    buttons.ibutton("📋 Set Max Tasks",             f"bw {user_id} set tasks")
    buttons.ibutton("🟡 Set Medium Speed",          f"bw {user_id} set medium")
    buttons.ibutton("🔴 Set Low Speed",             f"bw {user_id} set low")
    buttons.ibutton("🔄 Check Now",                 f"bw {user_id} refresh")
    buttons.ibutton("❌ Close",                     f"bw {user_id} close")
    return buttons.build(2)


_waiting: dict = {}


# ─────────────────────────────────────────
#  COMMAND HANDLER
# ─────────────────────────────────────────

async def bandwidth_command(client, message):
    await sendMessage(message, _status_text(), _menu_buttons(message.from_user.id))


# ─────────────────────────────────────────
#  CALLBACK HANDLER
# ─────────────────────────────────────────

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
            level = _decide_level(m)
            await _apply_limit(level)
        except Exception:
            pass
        await editMessage(query.message, _status_text(), _menu_buttons(user_id))
        return await query.answer("Checked & applied!", show_alert=True)

    if action == 'set':
        what = data[3] if len(data) > 3 else ''
        _waiting[user_id] = what
        prompts = {
            'cpu':    "🖥️ Send CPU threshold % (e.g. <code>80</code>)",
            'ram':    "💾 Send RAM threshold % (e.g. <code>85</code>)",
            'tasks':  "📋 Send max active tasks before throttle (e.g. <code>5</code>)",
            'medium': "🟡 Send Medium speed limit (e.g. <code>50MB</code> or <code>10240KB</code>)",
            'low':    "🔴 Send Low speed limit (e.g. <code>10MB</code> or <code>5120KB</code>)",
        }
        cancel_btn = ButtonMaker()
        cancel_btn.ibutton("❌ Cancel", f"bw {user_id} back")
        await editMessage(query.message, prompts.get(what, 'Send value:'), cancel_btn.build(1))
        return await query.answer()

    if action == 'back':
        await editMessage(query.message, _status_text(), _menu_buttons(user_id))
        return await query.answer()

    await query.answer()


# ─────────────────────────────────────────
#  INPUT HANDLER
# ─────────────────────────────────────────

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
            return await sendMessage(message, "❌ Enter a number between 1 and 99.")
        key = 'BW_CPU_HIGH' if what == 'cpu' else 'BW_RAM_HIGH'
        config_dict[key] = val
        if DATABASE_URL:
            await DbManger().update_config({key: val})
        await sendMessage(message, f"✅ {key} set to <b>{val}%</b>")

    elif what == 'tasks':
        try:
            val = int(text)
            assert val >= 1
        except Exception:
            return await sendMessage(message, "❌ Enter a positive integer.")
        config_dict['BW_MAX_TASKS_FULL'] = val
        if DATABASE_URL:
            await DbManger().update_config({'BW_MAX_TASKS_FULL': val})
        await sendMessage(message, f"✅ Max tasks set to <b>{val}</b>")

    elif what in ('medium', 'low'):
        bps = _parse_speed(text)
        if bps is None or bps < 0:
            return await sendMessage(message, "❌ Invalid speed. Use: <code>10MB</code>, <code>5120KB</code>")
        key = 'BW_SPEED_MEDIUM' if what == 'medium' else 'BW_SPEED_LOW'
        config_dict[key] = bps
        if DATABASE_URL:
            await DbManger().update_config({key: bps})
        await sendMessage(message, f"✅ {what.capitalize()} speed set to <b>{_fmt(bps)}</b>")


# ─────────────────────────────────────────
#  REGISTER HANDLERS
# ─────────────────────────────────────────

def add_handlers():
    bot.add_handler(
        MessageHandler(bandwidth_command,
                       filters=command(BotCommands.BandwidthCommand) & CustomFilters.sudo)
    )
    bot.add_handler(
        CallbackQueryHandler(bandwidth_callback, filters=regex(r'^bw '))
    )
    bot.add_handler(
        MessageHandler(bandwidth_input_handler, filters=CustomFilters.sudo)
    )
