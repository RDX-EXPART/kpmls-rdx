#!/usr/bin/env python3
"""
features_loader.py — সব নতুন feature module এক জায়গায় load করে।

__main__.py তে একবার `await load_all()` call করলেই:
  1. get_readable_message monkey-patch হয় (inline buttons)
  2. সব background task start হয়
  3. সব handler register হয়
  4. BotCommands এ নতুন command attribute inject হয়

Fix v3:
  - BotCommands class এ AutoThemeCommand / BandwidthCommand / SessionInfoCommand
    attribute না থাকলে নিজে add করে (bot_commands.py edit করতে হবে না)
  - প্রতিটো add_handlers() try-except এ wrap করা
"""

import asyncio
from bot import config_dict, LOGGER

# ─────────────────────────────────────────
#  STEP 0: BotCommands ATTRIBUTE INJECTION
#  bot_commands.py তে manually add না করেও কাজ করবে
# ─────────────────────────────────────────

def _inject_bot_commands():
    try:
        from bot.helper.telegram_helper import bot_commands as _bc_mod
        BC = _bc_mod.BotCommands
        suffix = str(config_dict.get('CMD_SUFFIX', '4'))

        _new_cmds = {
            'AutoThemeCommand':  f'autotheme{suffix}',
            'BandwidthCommand':  f'bandwidth{suffix}',
            'SessionInfoCommand': f'sessioninfo{suffix}',
        }
        for attr, val in _new_cmds.items():
            if not hasattr(BC, attr):
                setattr(BC, attr, val)
                LOGGER.info(f"[FeaturesLoader] Injected BotCommands.{attr} = /{val}")
    except Exception as e:
        LOGGER.warning(f"[FeaturesLoader] BotCommands inject failed: {e}")


# ─────────────────────────────────────────
#  STEP 1: get_readable_message MONKEY-PATCH
#  inline buttons status message এ দেখানোর জন্য
# ─────────────────────────────────────────

def _patch_readable_message():
    try:
        import bot.helper.telegram_helper.message_utils as _mu
        from bot.helper.telegram_helper.button_build import ButtonMaker
        from bot import download_dict, download_dict_lock, LOGGER as _LOG

        _original_grm = _mu.get_readable_message

        async def _patched_get_readable_message(*args, **kwargs):
            result = await _original_grm(*args, **kwargs)
            if result is None:
                return result
            msg, buttons = result if isinstance(result, tuple) else (result, None)

            try:
                async with download_dict_lock:
                    tasks = list(download_dict.items())
            except Exception:
                tasks = []

            if not tasks:
                return (msg, buttons) if isinstance(result, tuple) else msg

            bm = ButtonMaker()
            for gid, dl in tasks:
                try:
                    from bot.modules.inline_task_control import is_pausable
                    name = str(dl.name())[:18]
                    uid  = dl.message.from_user.id

                    if is_pausable(dl):
                        bm.ibutton(f"⏸ {name}", f"itc pause {gid} {uid}")
                    bm.ibutton(f"❌ Cancel", f"itc cancel {gid} {uid}")
                except Exception:
                    pass

            if bm._list:
                new_buttons = bm.build(2)
                return (msg, new_buttons) if isinstance(result, tuple) else (msg, new_buttons)

            return result

        _mu.get_readable_message = _patched_get_readable_message
        LOGGER.info("[FeaturesLoader] ✅ get_readable_message patched.")
    except Exception as e:
        LOGGER.error(f"[FeaturesLoader] Patch failed: {e}")


# ─────────────────────────────────────────
#  STEP 2: LOAD ALL FEATURES
# ─────────────────────────────────────────

async def load_all():
    LOGGER.info("[FeaturesLoader] ── Starting feature load ──")

    # BotCommands attribute injection (before any handler registration)
    _inject_bot_commands()

    # Monkey-patch get_readable_message
    _patch_readable_message()

    # ── Auto Theme ──────────────────────────
    try:
        from bot.modules.auto_theme import inject_defaults, auto_theme_loop, add_handlers as at_handlers
        inject_defaults()
        asyncio.create_task(auto_theme_loop())
        at_handlers()
        LOGGER.info("[FeaturesLoader] ✅ auto_theme loaded.")
    except Exception as e:
        LOGGER.error(f"[FeaturesLoader] auto_theme FAILED: {e}")

    # ── Bandwidth Manager ───────────────────
    try:
        from bot.modules.bandwidth_manager import inject_defaults as bw_defaults, bw_manager_loop, add_handlers as bw_handlers
        bw_defaults()
        asyncio.create_task(bw_manager_loop())
        bw_handlers()
        LOGGER.info("[FeaturesLoader] ✅ bandwidth_manager loaded.")
    except Exception as e:
        LOGGER.error(f"[FeaturesLoader] bandwidth_manager FAILED: {e}")

    # ── Inline Task Control ─────────────────
    try:
        from bot.modules.inline_task_control import add_handlers as itc_handlers
        itc_handlers()
        LOGGER.info("[FeaturesLoader] ✅ inline_task_control loaded.")
    except Exception as e:
        LOGGER.error(f"[FeaturesLoader] inline_task_control FAILED: {e}")

    # ── Session Restore ─────────────────────
    try:
        from bot.modules.session_restore import restore_sessions, add_handlers as sr_handlers
        await restore_sessions()
        sr_handlers()
        LOGGER.info("[FeaturesLoader] ✅ session_restore loaded.")
    except Exception as e:
        LOGGER.error(f"[FeaturesLoader] session_restore FAILED: {e}")

    LOGGER.info("[FeaturesLoader] ── All features loaded ──")
