#!/usr/bin/env python3
"""
features_loader.py — Auto Theme, Bandwidth Manager, Session Restore load করে।
(Inline buttons বাদ দেওয়া হয়েছে)
"""

import asyncio
from bot import config_dict, LOGGER


# ─────────────────────────────────────────
#  BotCommands ATTRIBUTE INJECTION
# ─────────────────────────────────────────

def _inject_bot_commands():
    try:
        from bot.helper.telegram_helper import bot_commands as _bc_mod
        BC     = _bc_mod.BotCommands
        suffix = str(config_dict.get('CMD_SUFFIX', '4'))
        _new   = {
            'AutoThemeCommand':   f'autotheme{suffix}',
            'BandwidthCommand':   f'bandwidth{suffix}',
            'SessionInfoCommand': f'sessioninfo{suffix}',
        }
        for attr, val in _new.items():
            if not hasattr(BC, attr):
                setattr(BC, attr, val)
                LOGGER.info(f"[FeaturesLoader] Injected BotCommands.{attr} = /{val}")
    except Exception as e:
        LOGGER.warning(f"[FeaturesLoader] BotCommands inject failed: {e}")


# ─────────────────────────────────────────
#  LOAD ALL FEATURES
# ─────────────────────────────────────────

async def load_all():
    LOGGER.info("[FeaturesLoader] ── Starting feature load ──")

    _inject_bot_commands()

    # ── Auto Theme ──────────────────────────
    try:
        from bot.modules.auto_theme import inject_defaults, auto_theme_loop, add_handlers as at_h
        inject_defaults()
        asyncio.create_task(auto_theme_loop())
        at_h()
        LOGGER.info("[FeaturesLoader] ✅ auto_theme loaded.")
    except Exception as e:
        LOGGER.error(f"[FeaturesLoader] auto_theme FAILED: {e}")

    # ── Bandwidth Manager ───────────────────
    try:
        from bot.modules.bandwidth_manager import inject_defaults as bw_d, bw_manager_loop, add_handlers as bw_h
        bw_d()
        asyncio.create_task(bw_manager_loop())
        bw_h()
        LOGGER.info("[FeaturesLoader] ✅ bandwidth_manager loaded.")
    except Exception as e:
        LOGGER.error(f"[FeaturesLoader] bandwidth_manager FAILED: {e}")

    # ── Session Restore ─────────────────────
    try:
        from bot.modules.session_restore import restore_sessions, add_handlers as sr_h
        await restore_sessions()
        sr_h()
        LOGGER.info("[FeaturesLoader] ✅ session_restore loaded.")
    except Exception as e:
        LOGGER.error(f"[FeaturesLoader] session_restore FAILED: {e}")

    LOGGER.info("[FeaturesLoader] ── All features loaded ──")
