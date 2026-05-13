#!/usr/bin/env python3
"""
AI Caption per-user settings handler for KPSML-X.

This module provides:
  1. get_ai_caption_buttons()  — inline keyboard for the AI Caption settings menu
  2. ai_caption_callback()     — Pyrogram callback query handler (regex: ^aicap)
  3. show_ai_caption_menu()    — helper to send/edit the menu message

HOW TO INTEGRATE into users_settings.py
----------------------------------------
See AI_CAPTION_USERS_SETTINGS_PATCH.md (in repo root) for the exact
copy-paste snippets to add to your users_settings.py.

Alternatively, register this module's handler independently by adding
to the bottom of this file (or your bot's __main__.py):

    from bot.helper.ext_utils.ai_caption_settings import register_ai_caption_handler
    register_ai_caption_handler(bot)
"""

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery

from bot import config_dict, LOGGER, user_data
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.message_utils import sendMessage, editMessage


# ─────────────────────────────────────────────────────
#  Status helpers
# ─────────────────────────────────────────────────────

def _global_ai_caption_on() -> bool:
    return bool(config_dict.get('AI_CAPTION', False))


def _user_ai_caption_state(user_id: int) -> str:
    """
    Returns one of:
      'on'     - user explicitly enabled
      'off'    - user explicitly disabled
      'global' - user hasn't set it; follows global config
    """
    val = user_data.get(user_id, {}).get('ai_caption', '')
    if val == '':
        return 'global'
    return 'on' if val else 'off'


def _effective_label(user_id: int) -> str:
    state = _user_ai_caption_state(user_id)
    if state == 'on':
        return '✅ ON (User)'
    if state == 'off':
        return '❌ OFF (User)'
    # global fallback
    return '✅ Global ON' if _global_ai_caption_on() else '❌ Global OFF'


# ─────────────────────────────────────────────────────
#  Keyboard builder
# ─────────────────────────────────────────────────────

def get_ai_caption_buttons(user_id: int) -> InlineKeyboardMarkup:
    state = _user_ai_caption_state(user_id)
    global_on = _global_ai_caption_on()

    # Toggle button label
    if state == 'on':
        toggle_label = '🔴 Disable AI Caption'
        toggle_data = 'aicap_off'
    elif state == 'off':
        toggle_label = '🟢 Enable AI Caption'
        toggle_data = 'aicap_on'
    else:
        # following global — offer to explicitly override
        if global_on:
            toggle_label = '🔴 Force OFF for Me'
            toggle_data = 'aicap_off'
        else:
            toggle_label = '🟢 Force ON for Me'
            toggle_data = 'aicap_on'

    rows = [
        [InlineKeyboardButton(toggle_label, callback_data=toggle_data)],
        [InlineKeyboardButton('🔄 Reset to Global Default', callback_data='aicap_reset')],
        [InlineKeyboardButton('◀️ Back', callback_data='userset_back')],
    ]
    return InlineKeyboardMarkup(rows)


# ─────────────────────────────────────────────────────
#  Menu text builder
# ─────────────────────────────────────────────────────

def _menu_text(user_id: int) -> str:
    state = _user_ai_caption_state(user_id)
    global_on = _global_ai_caption_on()
    effective = '✅ Enabled' if (state == 'on' or (state == 'global' and global_on)) else '❌ Disabled'

    state_label = {
        'on': '✅ ON <i>(overridden by you)</i>',
        'off': '❌ OFF <i>(overridden by you)</i>',
        'global': f'<i>Following global → </i>{"✅ ON" if global_on else "❌ OFF"}',
    }[state]

    return (
        f"🤖 <b>AI Caption Settings</b>\n\n"
        f"<b>Your Setting:</b> {state_label}\n"
        f"<b>Effective:</b> {effective}\n\n"
        f"<i>When enabled, leech uploads get auto-styled captions:\n"
        f"🎬 Title (Year)\n"
        f"🌟 IMDB Rating\n"
        f"🎞 Quality | 🔊 Audio | 📦 Size</i>"
    )


# ─────────────────────────────────────────────────────
#  Callback handler
# ─────────────────────────────────────────────────────

async def ai_caption_callback(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    data = query.data

    try:
        from bot.helper.ext_utils.db_handler import DbManger
        from bot.helper.ext_utils.bot_utils import update_user_ldata
    except ImportError:
        await query.answer("❌ Internal import error.", show_alert=True)
        return

    if data == 'aicap_on':
        update_user_ldata(user_id, 'ai_caption', True)
        await DbManger().update_user_data(user_id)
        await query.answer("✅ AI Caption enabled for your uploads!", show_alert=False)

    elif data == 'aicap_off':
        update_user_ldata(user_id, 'ai_caption', False)
        await DbManger().update_user_data(user_id)
        await query.answer("❌ AI Caption disabled for your uploads.", show_alert=False)

    elif data == 'aicap_reset':
        update_user_ldata(user_id, 'ai_caption', '')
        await DbManger().update_user_data(user_id)
        global_on = _global_ai_caption_on()
        await query.answer(
            f"🔄 Reset! Now following global setting ({'ON' if global_on else 'OFF'}).",
            show_alert=False,
        )

    elif data == 'aicap_menu':
        pass  # just re-render

    else:
        await query.answer()
        return

    await query.message.edit_text(
        _menu_text(user_id),
        reply_markup=get_ai_caption_buttons(user_id),
    )


# ─────────────────────────────────────────────────────
#  Standalone registration (optional)
# ─────────────────────────────────────────────────────

def register_ai_caption_handler(bot: Client):
    """
    Register the AI Caption callback handler on the given Pyrogram Client.
    Call this from your bot's startup if you are NOT integrating via users_settings.py.
    """
    bot.add_handler(
        __import__('pyrogram.handlers', fromlist=['CallbackQueryHandler']).CallbackQueryHandler(
            ai_caption_callback,
            filters.regex(r'^aicap'),
        )
    )
    LOGGER.info("AI Caption user-settings handler registered.")
