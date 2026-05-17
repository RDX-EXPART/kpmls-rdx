#!/usr/bin/env python3
"""
features_loader.py — Single entry-point for all 4 new features.

User শুধু __main__.py তে এই একটা line যোগ করবেন:

    from bot.modules import features_loader

এটা automatically সব করবে:
  1. Inline Buttons (Pause/Resume/Cancel/Retry) → status message এ
  2. /autotheme command + background loop
  3. /bandwidth command + background loop
  4. /sessioninfo command + startup restore
"""

from asyncio import create_task
from bot import LOGGER, config_dict, download_dict

# ─────────────────────────────────────────────────────────────────────
#  STEP 1: Patch message_utils.get_readable_message
#  (message_utils imports get_readable_message as a local reference,
#   তাই bot_utils.py edit করলে কাজ হয় না — এখানে সরাসরি patch করতে হয়)
# ─────────────────────────────────────────────────────────────────────

def _patch_inline_buttons():
    try:
        import bot.helper.telegram_helper.message_utils as _mu
        from bot.helper.telegram_helper.button_build import ButtonMaker

        _orig_get_readable_message = _mu.get_readable_message

        def _patched_get_readable_message():
            msg, button = _orig_get_readable_message()
            if msg is None or not download_dict:
                return msg, button

            try:
                from bot.helper.ext_utils.bot_utils import STATUS_START, STATUS_LIMIT as _SL
                _limit = config_dict.get('STATUS_LIMIT', 4)
                task_list = list(download_dict.values())[STATUS_START:_limit + STATUS_START]
            except Exception:
                task_list = list(download_dict.values())[:4]

            if not task_list:
                return msg, button

            try:
                from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

                # ── Rebuild keyboard: keep original rows + add task rows ──
                existing_rows = []
                if button and hasattr(button, 'inline_keyboard'):
                    existing_rows = list(button.inline_keyboard)

                task_rows = []
                for dl in task_list:
                    try:
                        gid      = dl.gid()
                        uid_task = dl.message.from_user.id
                        tname    = str(dl.name())
                        label    = (tname[:18] + "…") if len(tname) > 18 else tname
                        tstatus  = str(dl.status())

                        if tstatus == "Pause":
                            left_btn = InlineKeyboardButton(
                                f"▶ {label}",
                                callback_data=f"itc resume {gid} {uid_task}"
                            )
                        else:
                            left_btn = InlineKeyboardButton(
                                f"⏸ {label}",
                                callback_data=f"itc pause {gid} {uid_task}"
                            )
                        right_btn = InlineKeyboardButton(
                            "❌ Cancel",
                            callback_data=f"itc cancel {gid} {uid_task}"
                        )
                        task_rows.append([left_btn, right_btn])
                    except Exception:
                        pass

                if task_rows:
                    new_keyboard = InlineKeyboardMarkup(existing_rows + task_rows)
                    return msg, new_keyboard

            except Exception as e:
                LOGGER.warning(f"[FeaturesLoader] Inline button inject error: {e}")

            return msg, button

        _mu.get_readable_message = _patched_get_readable_message
        LOGGER.info("[FeaturesLoader] ✅ Inline Task Buttons patched into message_utils.")
        return True
    except Exception as e:
        LOGGER.error(f"[FeaturesLoader] ❌ Inline button patch failed: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────
#  STEP 2: Register inline_task_control callback handler
# ─────────────────────────────────────────────────────────────────────

def _register_inline_task_control():
    try:
        from bot.modules.inline_task_control import add_handlers
        add_handlers()
        return True
    except Exception as e:
        LOGGER.error(f"[FeaturesLoader] ❌ InlineTaskControl handler failed: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────
#  STEP 3: Auto Theme
# ─────────────────────────────────────────────────────────────────────

def _load_auto_theme():
    try:
        from bot.modules.auto_theme import (
            inject_defaults as at_inject,
            auto_theme_loop,
            add_handlers as at_handlers,
        )
        at_inject()
        create_task(auto_theme_loop())
        at_handlers()
        LOGGER.info("[FeaturesLoader] ✅ Auto Theme loaded.")
        return True
    except Exception as e:
        LOGGER.error(f"[FeaturesLoader] ❌ Auto Theme failed: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────
#  STEP 4: Bandwidth Manager
# ─────────────────────────────────────────────────────────────────────

def _load_bandwidth_manager():
    try:
        from bot.modules.bandwidth_manager import (
            inject_defaults as bw_inject,
            bw_manager_loop,
            add_handlers as bw_handlers,
        )
        bw_inject()
        create_task(bw_manager_loop())
        bw_handlers()
        LOGGER.info("[FeaturesLoader] ✅ Bandwidth Manager loaded.")
        return True
    except Exception as e:
        LOGGER.error(f"[FeaturesLoader] ❌ Bandwidth Manager failed: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────
#  STEP 5: Session Restore
# ─────────────────────────────────────────────────────────────────────

async def _load_session_restore():
    try:
        from bot.modules.session_restore import (
            inject_defaults as sr_inject,
            SessionRestore,
            add_handlers as sr_handlers,
        )
        sr_inject()
        sr = SessionRestore()
        await sr.restore_on_startup()
        sr_handlers()
        LOGGER.info("[FeaturesLoader] ✅ Session Restore loaded.")
        return True
    except Exception as e:
        LOGGER.error(f"[FeaturesLoader] ❌ Session Restore failed: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────
#  MAIN LOADER — call this from __main__.py's main() function
# ─────────────────────────────────────────────────────────────────────

async def load_all():
    """
    __main__.py এর main() function এ call করুন:

        from bot.modules.features_loader import load_all
        await load_all()
    """
    LOGGER.info("[FeaturesLoader] Loading new features...")

    results = {
        "inline_patch":   _patch_inline_buttons(),
        "inline_handler": _register_inline_task_control(),
        "auto_theme":     _load_auto_theme(),
        "bandwidth":      _load_bandwidth_manager(),
    }
    await _load_session_restore()

    ok  = sum(1 for v in results.values() if v)
    all = len(results) + 1  # +1 for session restore
    LOGGER.info(f"[FeaturesLoader] Done: {ok+1}/{all+1} features loaded.")
