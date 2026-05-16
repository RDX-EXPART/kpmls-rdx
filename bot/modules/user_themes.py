#!/usr/bin/env python3
"""
Feature: User Custom Themes
Command: /mytheme — lets each user customize their own bot UI style.

Customizable options:
  • progress_style  — progress bar appearance
  • emoji_pack      — emoji set used in status messages
  • caption_style   — caption format for uploaded files
"""

from asyncio import sleep
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.filters import command, regex

from bot import bot, user_data, LOGGER, DATABASE_URL
from bot.helper.telegram_helper.message_utils import sendMessage, editMessage, deleteMessage
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.ext_utils.bot_utils import update_user_ldata
from bot.helper.ext_utils.db_handler import DbManger

# ────────────────────────────────────────────
#  PROGRESS BAR STYLES
# ────────────────────────────────────────────
PROGRESS_STYLES = {
    'star': {
        'name': '⭐ Star (Default)',
        'filled': '★', 'empty': '✧',
        'prefix': '〔', 'suffix': '〕',
        'low': '🟢', 'mid': '🟡', 'high': '🔴',
    },
    'classic': {
        'name': '▓ Classic',
        'filled': '▓', 'empty': '░',
        'prefix': '[', 'suffix': ']',
        'low': '🟢', 'mid': '🟡', 'high': '🔴',
    },
    'blocks': {
        'name': '█ Blocks',
        'filled': '█', 'empty': '░',
        'prefix': '⟦', 'suffix': '⟧',
        'low': '💚', 'mid': '💛', 'high': '❤️',
    },
    'dots': {
        'name': '● Dots',
        'filled': '●', 'empty': '○',
        'prefix': '(', 'suffix': ')',
        'low': '🟢', 'mid': '🟡', 'high': '🔴',
    },
    'arrows': {
        'name': '▶ Arrows',
        'filled': '▶', 'empty': '─',
        'prefix': '⟨', 'suffix': '⟩',
        'low': '🚀', 'mid': '⚡', 'high': '🔥',
    },
    'fire': {
        'name': '🔥 Fire',
        'filled': '🔥', 'empty': '💧',
        'prefix': '', 'suffix': '',
        'low': '✅', 'mid': '⚠️', 'high': '🆘',
    },
    'minimal': {
        'name': '━ Minimal',
        'filled': '━', 'empty': '─',
        'prefix': '', 'suffix': '',
        'low': '◉', 'mid': '◉', 'high': '◉',
    },
    'neon': {
        'name': '◆ Neon',
        'filled': '◆', 'empty': '◇',
        'prefix': '【', 'suffix': '】',
        'low': '🔵', 'mid': '🟣', 'high': '🔴',
    },
}

# ────────────────────────────────────────────
#  EMOJI PACKS
# ────────────────────────────────────────────
EMOJI_PACKS = {
    'default': {
        'name': '😊 Default',
        'upload': '📤', 'download': '📥', 'done': '✅',
        'error': '❌', 'wait': '⏳', 'speed': '⚡',
        'size': '📦', 'time': '⏰', 'file': '📁',
        'progress': '📊', 'cancel': '🚫', 'seed': '🌱',
    },
    'fire': {
        'name': '🔥 Fire',
        'upload': '🔥', 'download': '⬇️', 'done': '🎉',
        'error': '💥', 'wait': '🔄', 'speed': '🚀',
        'size': '💾', 'time': '⏱️', 'file': '📂',
        'progress': '📈', 'cancel': '💀', 'seed': '🌿',
    },
    'space': {
        'name': '🚀 Space',
        'upload': '🛸', 'download': '🌠', 'done': '🌌',
        'error': '☄️', 'wait': '🌙', 'speed': '⭐',
        'size': '🪐', 'time': '🕐', 'file': '🗂️',
        'progress': '🔭', 'cancel': '💫', 'seed': '🌍',
    },
    'minimal': {
        'name': '· Minimal',
        'upload': '↑', 'download': '↓', 'done': '✓',
        'error': '✗', 'wait': '·', 'speed': '»',
        'size': '#', 'time': '@', 'file': '/',
        'progress': '%', 'cancel': 'X', 'seed': 'S',
    },
    'cute': {
        'name': '🌸 Cute',
        'upload': '🌸', 'download': '💫', 'done': '🌟',
        'error': '😿', 'wait': '🌀', 'speed': '💨',
        'size': '🎀', 'time': '🕐', 'file': '📋',
        'progress': '🌈', 'cancel': '💔', 'seed': '🌺',
    },
}

# ────────────────────────────────────────────
#  CAPTION STYLES
# ────────────────────────────────────────────
CAPTION_STYLES = {
    'default': {
        'name': '📄 Default',
        'description': 'Standard bot caption style',
    },
    'minimal': {
        'name': '📝 Minimal',
        'description': 'Clean, simple — just filename + size',
        'template': '<code>{filename}</code>\n💾 {size}',
    },
    'detailed': {
        'name': '📋 Detailed',
        'description': 'Full info — name, size, quality, language',
        'template': (
            '🎬 <b>{filename}</b>\n'
            '━━━━━━━━━━━━━━━\n'
            '💾 <b>Size:</b> {size}\n'
            '🎞 <b>Quality:</b> {quality}\n'
            '🗣 <b>Language:</b> {languages}\n'
            '━━━━━━━━━━━━━━━\n'
            '🤖 @{bot_username}'
        ),
    },
    'bold': {
        'name': '💪 Bold',
        'description': 'Big title + size, minimal extras',
        'template': '🔥 <b><u>{filename}</u></b>\n\n📦 <b>{size}</b>',
    },
    'card': {
        'name': '🎴 Card',
        'description': 'Boxed premium-feel caption',
        'template': (
            '╔══════════════════╗\n'
            '  🎬 <b>{filename}</b>\n'
            '╠══════════════════╣\n'
            '  💾 {size}\n'
            '╚══════════════════╝'
        ),
    },
}


# ────────────────────────────────────────────
#  BUTTON STYLES
#  Controls how many buttons appear per row
#  in upload-complete messages.
#  Default = 2 (matches the repo's existing style)
# ────────────────────────────────────────────
BUTTON_STYLES = {
    'default': {
        'name': '▦ Default (2 per row)',
        'cols': 2,
        'description': 'Standard layout — same as bot default',
    },
    'compact': {
        'name': '▤ Compact (3 per row)',
        'cols': 3,
        'description': 'More buttons per row, less scrolling',
    },
    'expanded': {
        'name': '▥ Expanded (1 per row)',
        'cols': 1,
        'description': 'Each button on its own line — easy to tap',
    },
}

# ────────────────────────────────────────────
#  HELPERS
# ────────────────────────────────────────────

def get_user_theme_config(user_id: int) -> dict:
    """Return the theme config dict for a user (with defaults)."""
    data = user_data.get(user_id, {})
    return data.get('theme_config', {
        'progress_style': 'star',
        'emoji_pack': 'default',
        'caption_style': 'default',
        'button_style': 'default',
    })


def get_user_progress_bar(pct, user_id: int, length: int = 12) -> str:
    """Return a progress bar string styled per user preference."""
    try:
        p = float(str(pct).strip('%'))
    except Exception:
        p = 0.0
    p = max(0.0, min(100.0, p))

    cfg = get_user_theme_config(user_id)
    style_key = cfg.get('progress_style', 'star')
    style = PROGRESS_STYLES.get(style_key, PROGRESS_STYLES['star'])

    filled_count = int(p / 100 * length)
    bar = style['filled'] * filled_count + style['empty'] * (length - filled_count)
    bar_str = f"{style['prefix']}{bar}{style['suffix']}"

    if p < 40:
        indicator = style['low']
    elif p < 75:
        indicator = style['mid']
    else:
        indicator = style['high']

    return f"{indicator}{bar_str}"


def get_user_emoji(user_id: int, key: str) -> str:
    """Get an emoji from the user's chosen emoji pack."""
    cfg = get_user_theme_config(user_id)
    pack_key = cfg.get('emoji_pack', 'default')
    pack = EMOJI_PACKS.get(pack_key, EMOJI_PACKS['default'])
    return pack.get(key, EMOJI_PACKS['default'].get(key, ''))


def get_user_caption_style(user_id: int) -> dict:
    """Return the caption style dict for a user."""
    cfg = get_user_theme_config(user_id)
    style_key = cfg.get('caption_style', 'default')
    return CAPTION_STYLES.get(style_key, CAPTION_STYLES['default'])




def get_user_button_cols(user_id: int) -> int:
    """Return the number of button columns for a user's upload messages."""
    cfg = get_user_theme_config(user_id)
    style_key = cfg.get('button_style', 'default')
    return BUTTON_STYLES.get(style_key, BUTTON_STYLES['default'])['cols']

def build_preview_message(style_key: str, pack_key: str, caption_key: str) -> str:
    """Build a live preview message for theme settings."""
    style = PROGRESS_STYLES.get(style_key, PROGRESS_STYLES['star'])
    pack = EMOJI_PACKS.get(pack_key, EMOJI_PACKS['default'])
    caption = CAPTION_STYLES.get(caption_key, CAPTION_STYLES['default'])

    length = 10
    sample_pct = 65
    filled = int(sample_pct / 100 * length)
    bar = style['filled'] * filled + style['empty'] * (length - filled)
    bar_str = f"{style['prefix']}{bar}{style['suffix']}"
    indicator = style['mid']

    btn_key = cfg.get('button_style', 'default') if cfg else 'default'
    btn_style = BUTTON_STYLES.get(btn_key, BUTTON_STYLES['default'])
    return (
        f"<b>🎨 Your Theme Preview</b>\n\n"
        f"<b>Progress Bar:</b>\n"
        f"{indicator}{bar_str} {sample_pct}%\n\n"
        f"<b>Emoji Pack:</b>\n"
        f"{pack['download']} Download  {pack['upload']} Upload  {pack['done']} Done\n"
        f"{pack['speed']} Speed  {pack['size']} Size  {pack['time']} ETA\n\n"
        f"<b>Caption Style:</b> {caption['name']}\n"
        f"<i>{caption['description']}</i>\n\n"
        f"<b>Button Style:</b> {btn_style['name']}\n"
        f"<i>{btn_style['description']}</i>"
    )

# ────────────────────────────────────────────
#  HANDLER STATE
# ────────────────────────────────────────────
handler_dict: dict = {}


async def save_user_theme(user_id: int, theme_config: dict):
    """Persist theme_config to user_data and DB."""
    update_user_ldata(user_id, 'theme_config', theme_config)
    if DATABASE_URL:
        await DbManger().update_user_data(user_id)


# ────────────────────────────────────────────
#  MAIN COMMAND HANDLER
# ────────────────────────────────────────────

async def mytheme_command(client, message):
    user_id = message.from_user.id
    cfg = get_user_theme_config(user_id)

    preview = build_preview_message(
        cfg['progress_style'],
        cfg['emoji_pack'],
        cfg['caption_style'],
    )

    buttons = ButtonMaker()
    buttons.ibutton("🎨 Progress Style", f"theme {user_id} section progress")
    buttons.ibutton("😊 Emoji Pack", f"theme {user_id} section emoji")
    buttons.ibutton("📄 Caption Style", f"theme {user_id} section caption")
    buttons.ibutton("▦ Button Style", f"theme {user_id} section button")
    buttons.ibutton("🔄 Reset to Default", f"theme {user_id} reset")
    buttons.ibutton("❌ Close", f"theme {user_id} close")

    await sendMessage(message, preview, buttons.build(2))


# ────────────────────────────────────────────
#  CALLBACK HANDLER
# ────────────────────────────────────────────

async def mytheme_callback(client, query):
    data = query.data.split()
    # data[0] = 'theme', data[1] = user_id, data[2] = action, data[3?] = value

    if len(data) < 3:
        return await query.answer("Invalid callback.", show_alert=True)

    user_id = int(data[1])

    if query.from_user.id != user_id:
        return await query.answer("This menu is not for you!", show_alert=True)

    action = data[2]

    if action == 'close':
        await deleteMessage(query.message)
        return await query.answer()

    if action == 'reset':
        default_cfg = {
            'progress_style': 'star',
            'emoji_pack': 'default',
            'caption_style': 'default',
        }
        await save_user_theme(user_id, default_cfg)
        preview = build_preview_message('star', 'default', 'default')
        buttons = ButtonMaker()
        buttons.ibutton("🎨 Progress Style", f"theme {user_id} section progress")
        buttons.ibutton("😊 Emoji Pack", f"theme {user_id} section emoji")
        buttons.ibutton("📄 Caption Style", f"theme {user_id} section caption")
        buttons.ibutton("🔄 Reset to Default", f"theme {user_id} reset")
        buttons.ibutton("❌ Close", f"theme {user_id} close")
        await editMessage(query.message, "✅ Theme reset to default!\n\n" + preview, buttons.build(2))
        return await query.answer("Reset done!")

    if action == 'section':
        section = data[3] if len(data) > 3 else ''
        cfg = get_user_theme_config(user_id)

        if section == 'progress':
            buttons = ButtonMaker()
            for key, s in PROGRESS_STYLES.items():
                label = ("✅ " if cfg['progress_style'] == key else "") + s['name']
                buttons.ibutton(label, f"theme {user_id} set progress {key}")
            buttons.ibutton("⬅️ Back", f"theme {user_id} back")
            preview = build_preview_message(cfg['progress_style'], cfg['emoji_pack'], cfg['caption_style'])
            await editMessage(query.message, f"<b>🎨 Choose Progress Bar Style</b>\n\n{preview}", buttons.build(2))

        elif section == 'emoji':
            buttons = ButtonMaker()
            for key, p in EMOJI_PACKS.items():
                label = ("✅ " if cfg['emoji_pack'] == key else "") + p['name']
                buttons.ibutton(label, f"theme {user_id} set emoji {key}")
            buttons.ibutton("⬅️ Back", f"theme {user_id} back")
            preview = build_preview_message(cfg['progress_style'], cfg['emoji_pack'], cfg['caption_style'])
            await editMessage(query.message, f"<b>😊 Choose Emoji Pack</b>\n\n{preview}", buttons.build(2))

        elif section == 'caption':
            buttons = ButtonMaker()
            for key, cs in CAPTION_STYLES.items():
                label = ("✅ " if cfg['caption_style'] == key else "") + cs['name']
                buttons.ibutton(label, f"theme {user_id} set caption {key}")
            buttons.ibutton("⬅️ Back", f"theme {user_id} back")
            preview = build_preview_message(cfg['progress_style'], cfg['emoji_pack'], cfg['caption_style'])
            await editMessage(query.message, f"<b>📄 Choose Caption Style</b>\n\n{preview}", buttons.build(2))

        elif section == 'button':
            buttons = ButtonMaker()
            for key, bs in BUTTON_STYLES.items():
                label = ("✅ " if cfg.get('button_style', 'default') == key else "") + bs['name']
                buttons.ibutton(label, f"theme {user_id} set button {key}")
            buttons.ibutton("⬅️ Back", f"theme {user_id} back")
            preview = build_preview_message(cfg['progress_style'], cfg['emoji_pack'], cfg['caption_style'])
            await editMessage(query.message, f"<b>▦ Choose Button Style</b>\n\n{preview}", buttons.build(1))

        return await query.answer()

    if action == 'set':
        if len(data) < 5:
            return await query.answer("Invalid.", show_alert=True)
        category = data[3]
        value = data[4]
        cfg = get_user_theme_config(user_id)

        if category == 'progress' and value in PROGRESS_STYLES:
            cfg['progress_style'] = value
        elif category == 'emoji' and value in EMOJI_PACKS:
            cfg['emoji_pack'] = value
        elif category == 'caption' and value in CAPTION_STYLES:
            cfg['caption_style'] = value
        elif category == 'button' and value in BUTTON_STYLES:
            cfg['button_style'] = value
        else:
            return await query.answer("Invalid option.", show_alert=True)

        await save_user_theme(user_id, cfg)

        # Refresh the section view
        buttons = ButtonMaker()
        if category == 'progress':
            for key, s in PROGRESS_STYLES.items():
                label = ("✅ " if cfg['progress_style'] == key else "") + s['name']
                buttons.ibutton(label, f"theme {user_id} set progress {key}")
        elif category == 'emoji':
            for key, p in EMOJI_PACKS.items():
                label = ("✅ " if cfg['emoji_pack'] == key else "") + p['name']
                buttons.ibutton(label, f"theme {user_id} set emoji {key}")
        elif category == 'caption':
            for key, cs in CAPTION_STYLES.items():
                label = ("✅ " if cfg['caption_style'] == key else "") + cs['name']
                buttons.ibutton(label, f"theme {user_id} set caption {key}")
        elif category == 'button':
            for key, bs in BUTTON_STYLES.items():
                label = ("✅ " if cfg.get('button_style','default') == key else "") + bs['name']
                buttons.ibutton(label, f"theme {user_id} set button {key}")

        buttons.ibutton("⬅️ Back", f"theme {user_id} back")
        preview = build_preview_message(cfg['progress_style'], cfg['emoji_pack'], cfg['caption_style'])
        section_titles = {'progress': '🎨 Progress Bar Style', 'emoji': '😊 Emoji Pack', 'caption': '📄 Caption Style', 'button': '▦ Button Style'}
        await editMessage(
            query.message,
            f"<b>{section_titles.get(category, '')} — saved!</b>\n\n{preview}",
            buttons.build(2),
        )
        return await query.answer("✅ Saved!")

    if action == 'back':
        cfg = get_user_theme_config(user_id)
        preview = build_preview_message(cfg['progress_style'], cfg['emoji_pack'], cfg['caption_style'])
        buttons = ButtonMaker()
        buttons.ibutton("🎨 Progress Style", f"theme {user_id} section progress")
        buttons.ibutton("😊 Emoji Pack", f"theme {user_id} section emoji")
        buttons.ibutton("📄 Caption Style", f"theme {user_id} section caption")
        buttons.ibutton("🔄 Reset to Default", f"theme {user_id} reset")
        buttons.ibutton("❌ Close", f"theme {user_id} close")
        await editMessage(query.message, preview, buttons.build(2))
        return await query.answer()

    await query.answer()


# ────────────────────────────────────────────
#  REGISTER HANDLERS
# ────────────────────────────────────────────

def add_handlers():
    bot.add_handler(
        MessageHandler(
            mytheme_command,
            filters=command(BotCommands.MyThemeCommand) & CustomFilters.authorized,
        )
    )
    bot.add_handler(
        CallbackQueryHandler(mytheme_callback, filters=regex(r'^theme'))
    )
