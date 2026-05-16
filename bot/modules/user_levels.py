#!/usr/bin/env python3
"""
Feature: User Level System
Command: /mylevel — shows your XP, level, badge, and progress to next level.

XP is earned automatically:
  • +10 XP  per completed task (upload/download/clone)
  • +5  XP  per GB transferred
  • +20 XP  daily login bonus (first /start or /mylevel of the day)

Levels & Badges:
  Level 1  🌱 Newbie        0    – 99  XP
  Level 2  🔰 Member       100  – 299 XP
  Level 3  ⚡ Active        300  – 699 XP
  Level 4  💎 Pro           700  – 1499 XP
  Level 5  🏆 Expert       1500 – 2999 XP
  Level 6  🔥 Elite        3000 – 5999 XP
  Level 7  👑 Legend VIP   6000+ XP
"""

from datetime import datetime, date
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.filters import command, regex

from bot import bot, user_data, LOGGER, DATABASE_URL
from bot.helper.telegram_helper.message_utils import sendMessage, editMessage, deleteMessage
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.ext_utils.bot_utils import update_user_ldata, get_readable_file_size
from bot.helper.ext_utils.db_handler import DbManger

# ────────────────────────────────────────────
#  LEVEL TABLE
# ────────────────────────────────────────────
LEVELS = [
    {'level': 1, 'badge': '🌱', 'title': 'Newbie',     'min_xp': 0,    'max_xp': 99},
    {'level': 2, 'badge': '🔰', 'title': 'Member',     'min_xp': 100,  'max_xp': 299},
    {'level': 3, 'badge': '⚡', 'title': 'Active',     'min_xp': 300,  'max_xp': 699},
    {'level': 4, 'badge': '💎', 'title': 'Pro',        'min_xp': 700,  'max_xp': 1499},
    {'level': 5, 'badge': '🏆', 'title': 'Expert',     'min_xp': 1500, 'max_xp': 2999},
    {'level': 6, 'badge': '🔥', 'title': 'Elite',      'min_xp': 3000, 'max_xp': 5999},
    {'level': 7, 'badge': '👑', 'title': 'Legend VIP', 'min_xp': 6000, 'max_xp': None},
]

DAILY_BONUS_XP   = 20
TASK_XP          = 10
XP_PER_GB        = 5
LEADERBOARD_SIZE = 10


# ────────────────────────────────────────────
#  CORE HELPERS
# ────────────────────────────────────────────

def get_level_info(xp: int) -> dict:
    """Return the level dict for the given XP amount."""
    for lvl in reversed(LEVELS):
        if xp >= lvl['min_xp']:
            return lvl
    return LEVELS[0]


def get_next_level(xp: int) -> dict | None:
    """Return the next level dict, or None if at max."""
    current = get_level_info(xp)
    idx = LEVELS.index(current)
    return LEVELS[idx + 1] if idx + 1 < len(LEVELS) else None


def xp_progress_bar(xp: int, length: int = 14) -> str:
    """Build an XP progress bar between current and next level."""
    current = get_level_info(xp)
    nxt = get_next_level(xp)
    if nxt is None:
        return '👑' * length  # max level

    span   = nxt['min_xp'] - current['min_xp']
    gained = xp - current['min_xp']
    ratio  = gained / span if span > 0 else 1.0

    filled = int(ratio * length)
    bar    = '█' * filled + '░' * (length - filled)
    pct    = int(ratio * 100)
    return f"[{bar}] {pct}%"


def get_user_xp_data(user_id: int) -> dict:
    """Return (xp, tasks_done, bytes_transferred) for a user."""
    data = user_data.get(user_id, {})
    return {
        'xp':          data.get('xp', 0),
        'tasks_done':  data.get('level_tasks', 0),
        'total_bytes': data.get('level_bytes', 0),
        'last_daily':  data.get('last_daily_bonus', ''),
    }


async def award_xp(user_id: int, task_size_bytes: int = 0):
    """
    Award XP for a completed task.
    Call this from tasks_listener.py after a successful upload/download.
    """
    data = get_user_xp_data(user_id)
    xp   = data['xp']
    old_level = get_level_info(xp)

    earned   = TASK_XP
    gb_count = task_size_bytes / (1024 ** 3)
    earned  += int(gb_count * XP_PER_GB)

    xp += earned
    tasks_done  = data['tasks_done'] + 1
    total_bytes = data['total_bytes'] + task_size_bytes

    update_user_ldata(user_id, 'xp', xp)
    update_user_ldata(user_id, 'level_tasks', tasks_done)
    update_user_ldata(user_id, 'level_bytes', total_bytes)

    if DATABASE_URL:
        await DbManger().update_user_data(user_id)

    new_level = get_level_info(xp)
    if new_level['level'] > old_level['level']:
        LOGGER.info(
            f"[Level Up] User {user_id} reached Level {new_level['level']} "
            f"{new_level['badge']} {new_level['title']}"
        )
        return new_level  # caller can optionally notify user
    return None


async def award_daily_bonus(user_id: int) -> bool:
    """
    Award daily XP bonus.  Returns True if bonus was given today.
    Call this from /start or /mylevel.
    """
    data  = get_user_xp_data(user_id)
    today = str(date.today())

    if data['last_daily'] == today:
        return False

    xp = data['xp'] + DAILY_BONUS_XP
    update_user_ldata(user_id, 'xp', xp)
    update_user_ldata(user_id, 'last_daily_bonus', today)

    if DATABASE_URL:
        await DbManger().update_user_data(user_id)

    LOGGER.info(f"[Daily Bonus] +{DAILY_BONUS_XP} XP awarded to user {user_id}")
    return True


def build_level_card(user_id: int, user_name: str) -> str:
    """Build the /mylevel display card."""
    data    = get_user_xp_data(user_id)
    xp      = data['xp']
    tasks   = data['tasks_done']
    tb      = data['total_bytes']
    current = get_level_info(xp)
    nxt     = get_next_level(xp)
    bar     = xp_progress_bar(xp)

    tb_str = get_readable_file_size(tb) if tb > 0 else '0B'

    lines = [
        f"<b>━━━━━━━━━━━━━━━━━━━</b>",
        f"  {current['badge']} <b>{current['title']}</b> — Level {current['level']}",
        f"<b>━━━━━━━━━━━━━━━━━━━</b>",
        f"",
        f"👤 <b>User:</b> {user_name}",
        f"✨ <b>XP:</b>  <code>{xp:,}</code>",
        f"",
        f"<b>Progress:</b>",
        f"<code>{bar}</code>",
    ]

    if nxt:
        needed = nxt['min_xp'] - xp
        lines += [
            f"",
            f"🎯 <b>Next level:</b> {nxt['badge']} {nxt['title']} (Level {nxt['level']})",
            f"📈 <b>XP needed:</b> <code>{needed:,}</code> more XP",
        ]
    else:
        lines += [
            f"",
            f"🏅 <b>You have reached the highest level!</b>",
        ]

    lines += [
        f"",
        f"<b>━━━━━━━━━━━━━━━━━━━</b>",
        f"📦 <b>Tasks Done:</b>  {tasks:,}",
        f"💾 <b>Total Transferred:</b> {tb_str}",
        f"<b>━━━━━━━━━━━━━━━━━━━</b>",
    ]

    return "\n".join(lines)


def get_user_badge(user_id: int) -> str:
    """Return just the badge emoji for a user (for inline display)."""
    xp  = user_data.get(user_id, {}).get('xp', 0)
    lvl = get_level_info(xp)
    return lvl['badge']


# ────────────────────────────────────────────
#  LEADERBOARD
# ────────────────────────────────────────────

def build_leaderboard() -> str:
    """Build a top-N leaderboard string."""
    entries = []
    for uid, data in user_data.items():
        xp = data.get('xp', 0)
        if xp > 0:
            entries.append((uid, xp))

    entries.sort(key=lambda x: x[1], reverse=True)
    top = entries[:LEADERBOARD_SIZE]

    if not top:
        return "🏆 <b>Leaderboard is empty!</b>\nComplete tasks to earn XP."

    ranks = ['🥇', '🥈', '🥉'] + [f'{i}.' for i in range(4, LEADERBOARD_SIZE + 1)]
    lines = ["<b>🏆 XP Leaderboard</b>\n"]
    for i, (uid, xp) in enumerate(top):
        lvl = get_level_info(xp)
        lines.append(f"{ranks[i]} {lvl['badge']} <code>{uid}</code> — <b>{xp:,} XP</b>")

    return "\n".join(lines)


# ────────────────────────────────────────────
#  COMMAND HANDLERS
# ────────────────────────────────────────────

async def mylevel_command(client, message):
    user_id   = message.from_user.id
    user_name = (
        message.from_user.username
        or message.from_user.first_name
        or str(user_id)
    )

    # Award daily bonus silently
    gave_bonus = await award_daily_bonus(user_id)

    card = build_level_card(user_id, user_name)

    if gave_bonus:
        card = f"🎁 <b>Daily Bonus!</b> +{DAILY_BONUS_XP} XP awarded!\n\n" + card

    buttons = ButtonMaker()
    buttons.ibutton("🏆 Leaderboard", f"level {user_id} lb")
    buttons.ibutton("❌ Close", f"level {user_id} close")

    await sendMessage(message, card, buttons.build(2))


async def level_callback(client, query):
    data = query.data.split()
    if len(data) < 3:
        return await query.answer()

    user_id = int(data[1])
    action  = data[2]

    if query.from_user.id != user_id:
        return await query.answer("This menu is not for you!", show_alert=True)

    if action == 'close':
        await deleteMessage(query.message)
        return await query.answer()

    if action == 'lb':
        lb_text = build_leaderboard()
        buttons = ButtonMaker()
        buttons.ibutton("⬅️ My Level", f"level {user_id} back")
        buttons.ibutton("❌ Close", f"level {user_id} close")
        await editMessage(query.message, lb_text, buttons.build(2))
        return await query.answer()

    if action == 'back':
        user_name = query.from_user.username or query.from_user.first_name or str(user_id)
        card = build_level_card(user_id, user_name)
        buttons = ButtonMaker()
        buttons.ibutton("🏆 Leaderboard", f"level {user_id} lb")
        buttons.ibutton("❌ Close", f"level {user_id} close")
        await editMessage(query.message, card, buttons.build(2))
        return await query.answer()

    await query.answer()


# ────────────────────────────────────────────
#  REGISTER HANDLERS
# ────────────────────────────────────────────

def add_handlers():
    bot.add_handler(
        MessageHandler(
            mylevel_command,
            filters=command(BotCommands.MyLevelCommand) & CustomFilters.authorized,
        )
    )
    bot.add_handler(
        CallbackQueryHandler(level_callback, filters=regex(r'^level'))
    )
