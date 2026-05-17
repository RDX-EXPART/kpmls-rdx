#!/usr/bin/env python3
"""
features_loader.py — সব নতুন feature module এক জায়গায় load করে।

__main__.py তে একবার `await load_all()` call করলেই:
  1. get_readable_message monkey-patch হয় (inline buttons)
  2. সব background task start হয়
  3. সব handler register হয়
  4. BotCommands এ নতুন command attribute inject হয়

CRITICAL FIX v4:
  - get_readable_message মূলত একটা SYNC function — sync_to_async() দিয়ে
    run_in_executor তে চলে। তাই patched version অবশ্যই sync হতে হবে।
    Async patch করলে "coroutines cannot be used with run_in_executor()" error আসে।
"""

import asyncio
from bot import config_dict, download_dict, LOGGER

# ─────────────────────────────────────────
#  STEP 0: BotCommands ATTRIBUTE INJECTION
# ─────────────────────────────────────────

def _inject_bot_commands():
    try:
        from bot.helper.telegram_helper import bot_commands as _bc_mod
        BC     = _bc_mod.BotCommands
        suffix = str(config_dict.get('CMD_SUFFIX', '4'))

        _new = {
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
#  STEP 1: get_readable_message MONKEY-PATCH
#
#  IMPORTANT: get_readable_message is a SYNC function called via sync_to_async()
#  which uses run_in_executor (thread pool). The patched version MUST also be
#  synchronous — if it's async, run_in_executor throws:
#    TypeError: coroutines cannot be used with run_in_executor()
# ─────────────────────────────────────────

def _patch_readable_message():
    try:
        import bot.helper.telegram_helper.message_utils as _mu
        from bot.helper.telegram_helper.button_build import ButtonMaker

        _original_grm = _mu.get_readable_message

        # ── SYNCHRONOUS patch ───────────────────────────────────────────────
        def _patched_get_readable_message(*args, **kwargs):
            # Call the original sync function
            result = _original_grm(*args, **kwargs)
            if result is None:
                return result

            msg, buttons = result if isinstance(result, tuple) else (result, None)

            # Access download_dict directly — safe in thread context
            try:
                tasks = list(download_dict.items())
            except Exception:
                tasks = []

            if not tasks:
                return (msg, buttons) if isinstance(result, tuple) else msg

            bm           = ButtonMaker()
            button_added = False
            for gid, dl in tasks:
                try:
                    from bot.modules.inline_task_control import is_pausable
                    name = str(dl.name())[:18]
                    uid  = dl.message.from_user.id
                    if is_pausable(dl):
                        bm.ibutton(f"⏸ {name}", f"itc pause {gid} {uid}")
                    bm.ibutton("❌ Cancel", f"itc cancel {gid} {uid}")
                    button_added = True
                except Exception:
                    pass

            if button_added:
                new_buttons = bm.build(2)
                return (msg, new_buttons) if isinstance(result, tuple) else (msg, new_buttons)

            return result
        # ───────────────────────────────────────────────────────────────────

        _mu.get_readable_message = _patched_get_readable_message
        LOGGER.info("[FeaturesLoader] ✅ get_readable_message patched (sync).")
    except Exception as e:
        LOGGER.error(f"[FeaturesLoader] Patch failed: {e}")


# ─────────────────────────────────────────
#  STEP 2: LOAD ALL FEATURES
# ─────────────────────────────────────────

async def load_all():
    LOGGER.info("[FeaturesLoader] ── Starting feature load ──")

    # BotCommands attribute injection (before any handler registration)
    _inject_bot_commands()

    # Monkey-patch get_readable_message (MUST be sync)
    _patch_readable_message()

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

    # ── Inline Task Control ─────────────────
    try:
        from bot.modules.inline_task_control import add_handlers as itc_h
        itc_h()
        LOGGER.info("[FeaturesLoader] ✅ inline_task_control loaded.")
    except Exception as e:
        LOGGER.error(f"[FeaturesLoader] inline_task_control FAILED: {e}")

    # ── Session Restore ─────────────────────
    try:
        from bot.modules.session_restore import restore_sessions, add_handlers as sr_h
        await restore_sessions()
        sr_h()
        LOGGER.info("[FeaturesLoader] ✅ session_restore loaded.")
    except Exception as e:
        LOGGER.error(f"[FeaturesLoader] session_restore FAILED: {e}")

    LOGGER.info("[FeaturesLoader] ── All features loaded ──")
