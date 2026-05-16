#!/usr/bin/env python3
"""
Modified themes/__init__.py
Adds per-user progress bar support via user_themes.py helpers.
The BotTheme() function is unchanged — it still handles text strings.
The new get_user_progress_bar() wrapper is imported here for convenience.
"""

from os import listdir
from importlib import import_module
from random import choice as rchoice
from bot import config_dict, LOGGER
from bot.helper.themes import kpsml_minimal

AVL_THEMES = {}
for theme in listdir('bot/helper/themes'):
    if theme.startswith('kpsml_') and theme.endswith('.py'):
        AVL_THEMES[theme[5:-3]] = import_module(f'bot.helper.themes.{theme[:-3]}')


def BotTheme(var_name, **format_vars):
    text = None
    theme_ = config_dict['BOT_THEME']

    if theme_ in AVL_THEMES:
        text = getattr(AVL_THEMES[theme_].KPSMLStyle(), var_name, None)
        if text is None:
            LOGGER.error(f"{var_name} not Found in {theme_}. Please recheck with Official Repo")
    elif theme_ == 'random':
        rantheme = rchoice(list(AVL_THEMES.values()))
        LOGGER.info(f"Random Theme Chosen: {rantheme}")
        text = getattr(rantheme.KPSMLStyle(), var_name, None)

    if text is None:
        text = getattr(kpsml_minimal.KPSMLStyle(), var_name)

    return text.format_map(format_vars)


# ─────────────────────────────────────────────────────
#  NEW: Per-user progress bar
#  Import and use get_user_progress_bar(pct, user_id)
#  anywhere you currently call get_progress_bar_string(pct).
#
#  Example usage in get_readable_message():
#      from bot.helper.themes import get_user_progress_bar
#      bar = get_user_progress_bar(pct, listener.message.from_user.id)
# ─────────────────────────────────────────────────────
def get_user_progress_bar(pct, user_id: int, length: int = 12) -> str:
    """
    Return a progress bar string styled according to the user's theme config.
    Falls back to the default star style if user has no preference set.
    """
    try:
        from bot.modules.user_themes import get_user_progress_bar as _impl
        return _impl(pct, user_id, length)
    except Exception:
        # Fallback: use the standard progress bar if user_themes not available
        from bot.helper.ext_utils.bot_utils import get_progress_bar_string
        return get_progress_bar_string(pct)
