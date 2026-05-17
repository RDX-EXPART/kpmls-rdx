#!/usr/bin/env python3
"""
Feature: Session Restore
Server restart হলেও task continue করবে।

কিভাবে কাজ করে:
  1. প্রতিটা task শুরু হলে MongoDB তে save হয়:
       - task_id (unique)
       - user_id, chat_id
       - original command text
       - task type (download/leech/mirror/etc.)
       - status (running/paused)
       - created_at
  2. Bot restart হলে saved tasks load করে → user কে notify করে
     এবং যে tasks গুলো auto-restartable সেগুলো automatically re-send করে।
  3. Task complete/cancel হলে DB থেকে delete হয়।

Integration in bot/__main__.py:
    from bot.modules.session_restore import (
        SessionRestore, inject_defaults as sr_inject
    )
    sr_inject()
    sr = SessionRestore()
    # On startup:
    await sr.restore_on_startup()
    # Register handlers:
    from bot.modules import session_restore as sr_mod
    sr_mod.add_handlers()

Usage in tasks_listener.py:
    from bot.modules.session_restore import sr_save_task, sr_remove_task
    # When task starts:
    await sr_save_task(task_id, user_id, chat_id, cmd_text, task_type)
    # When task ends:
    await sr_remove_task(task_id)
"""

from asyncio import sleep
from time import time
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from pyrogram.handlers import MessageHandler
from pyrogram.filters import command

from bot import bot, config_dict, bot_id, DATABASE_URL, LOGGER, download_dict
from bot.helper.telegram_helper.message_utils import sendMessage
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.ext_utils.bot_utils import get_readable_time

# ─────────────────────────────────────────
#  DEFAULT CONFIG
# ─────────────────────────────────────────
SR_DEFAULTS = {
    'SESSION_RESTORE':        True,
    'SR_AUTO_RETRY':          True,   # auto re-send restartable tasks
    'SR_NOTIFY_USER':         True,   # notify user on restore
    'SR_MAX_RESTORE_AGE_HRS': 24,     # ignore tasks older than N hours
}

# In-memory task registry (task_id → info dict)
# This is the source of truth; MongoDB is the persistent backup.
_task_registry: dict[str, dict] = {}

# ─────────────────────────────────────────
#  RESTARTABLE TASK TYPES
# ─────────────────────────────────────────
# These task types can be safely re-issued by re-sending the original command.
RESTARTABLE_TYPES = {'leech', 'mirror', 'ytdl', 'ytdlleech', 'clone'}


def inject_defaults():
    for k, v in SR_DEFAULTS.items():
        config_dict.setdefault(k, v)


# ─────────────────────────────────────────
#  DB HELPERS
# ─────────────────────────────────────────

def _get_db():
    """Return (client, collection) or (None, None) if no DATABASE_URL."""
    if not DATABASE_URL:
        return None, None
    try:
        client = AsyncIOMotorClient(DATABASE_URL)
        col    = client.kpsmlx.session_tasks[bot_id]
        return client, col
    except Exception as e:
        LOGGER.error(f"[SessionRestore] DB connect error: {e}")
        return None, None


async def sr_save_task(
    task_id: str,
    user_id: int,
    chat_id: int,
    command_text: str,
    task_type: str = 'leech',
    extra: dict | None = None,
):
    """
    Call when a new task starts.
    task_id   — unique ID (e.g. str(message.id) or gid)
    task_type — 'leech' | 'mirror' | 'ytdl' | etc.
    extra     — optional dict of extra info to store
    """
    if not config_dict.get('SESSION_RESTORE', True):
        return

    record = {
        '_id':          task_id,
        'user_id':      user_id,
        'chat_id':      chat_id,
        'command_text': command_text,
        'task_type':    task_type,
        'status':       'running',
        'created_at':   time(),
        'extra':        extra or {},
    }
    _task_registry[task_id] = record

    client, col = _get_db()
    if col is None:
        return
    try:
        await col.replace_one({'_id': task_id}, record, upsert=True)
    except Exception as e:
        LOGGER.error(f"[SessionRestore] save_task error: {e}")
    finally:
        client.close()


async def sr_remove_task(task_id: str):
    """Call when a task completes, is cancelled, or fails."""
    _task_registry.pop(task_id, None)

    client, col = _get_db()
    if col is None:
        return
    try:
        await col.delete_one({'_id': task_id})
    except Exception as e:
        LOGGER.error(f"[SessionRestore] remove_task error: {e}")
    finally:
        client.close()


async def sr_update_task_status(task_id: str, status: str):
    """Update status field (e.g. 'paused', 'running')."""
    if task_id in _task_registry:
        _task_registry[task_id]['status'] = status

    client, col = _get_db()
    if col is None:
        return
    try:
        await col.update_one({'_id': task_id}, {'$set': {'status': status}})
    except Exception as e:
        LOGGER.error(f"[SessionRestore] update_status error: {e}")
    finally:
        client.close()


# ─────────────────────────────────────────
#  SESSION RESTORE CLASS
# ─────────────────────────────────────────

class SessionRestore:

    async def restore_on_startup(self):
        """
        Call once on bot startup.
        Loads pending tasks from MongoDB, notifies users, and
        auto-retries restartable tasks if SR_AUTO_RETRY is enabled.
        """
        if not config_dict.get('SESSION_RESTORE', True):
            LOGGER.info("[SessionRestore] Feature disabled — skipping restore.")
            return

        client, col = _get_db()
        if col is None:
            LOGGER.info("[SessionRestore] No DATABASE_URL — skipping restore.")
            return

        try:
            max_age_hrs = config_dict.get('SR_MAX_RESTORE_AGE_HRS', 24)
            cutoff      = time() - (max_age_hrs * 3600)

            tasks = []
            async for row in col.find({'created_at': {'$gt': cutoff}}):
                tasks.append(row)

            if not tasks:
                LOGGER.info("[SessionRestore] No pending tasks to restore.")
                client.close()
                return

            LOGGER.info(f"[SessionRestore] Found {len(tasks)} pending task(s) to restore.")

            # group by user
            by_user: dict[int, list] = {}
            for t in tasks:
                by_user.setdefault(t['user_id'], []).append(t)

            for user_id, user_tasks in by_user.items():
                await self._handle_user_tasks(user_id, user_tasks)

            # Clear DB after restore attempt
            await col.delete_many({'created_at': {'$gt': cutoff}})

        except Exception as e:
            LOGGER.error(f"[SessionRestore] restore_on_startup error: {e}")
        finally:
            client.close()

    async def _handle_user_tasks(self, user_id: int, tasks: list):
        notify = config_dict.get('SR_NOTIFY_USER', True)
        auto_retry = config_dict.get('SR_AUTO_RETRY', True)

        for t in tasks:
            task_type = t.get('task_type', 'unknown')
            cmd_text  = t.get('command_text', '')
            chat_id   = t.get('chat_id')
            age_sec   = time() - t.get('created_at', 0)
            age_str   = get_readable_time(age_sec)

            LOGGER.info(
                f"[SessionRestore] Restoring task {t['_id']} "
                f"(type={task_type}, user={user_id}, age={age_str})"
            )

            if notify and chat_id:
                try:
                    msg = (
                        f"🔄 <b>Session Restore</b>\n\n"
                        f"Bot was restarted. Attempting to resume your task.\n\n"
                        f"<b>Task Type:</b> <code>{task_type}</code>\n"
                        f"<b>Age:</b> {age_str}\n"
                        f"<b>Command:</b> <code>{cmd_text[:200]}</code>"
                    )
                    await bot.send_message(chat_id=chat_id, text=msg)
                    await sleep(0.5)
                except Exception as e:
                    LOGGER.warning(f"[SessionRestore] Notify error for user {user_id}: {e}")

            if auto_retry and task_type in RESTARTABLE_TYPES and cmd_text and chat_id:
                try:
                    await sleep(2)
                    await bot.send_message(
                        chat_id=chat_id,
                        text=cmd_text,
                        disable_web_page_preview=True,
                    )
                    LOGGER.info(f"[SessionRestore] Auto-retried task {t['_id']}")
                except Exception as e:
                    LOGGER.error(f"[SessionRestore] Auto-retry error: {e}")
            elif task_type not in RESTARTABLE_TYPES and notify and chat_id:
                try:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=(
                            f"⚠️ <b>Task could not be auto-resumed</b>\n"
                            f"Type <code>{task_type}</code> requires manual restart.\n"
                            f"Original: <code>{cmd_text[:200]}</code>"
                        ),
                    )
                except Exception:
                    pass


# ─────────────────────────────────────────
#  /sessioninfo COMMAND
# ─────────────────────────────────────────

async def sessioninfo_command(client, message):
    enabled = config_dict.get('SESSION_RESTORE', True)
    auto_r  = config_dict.get('SR_AUTO_RETRY', True)
    notify  = config_dict.get('SR_NOTIFY_USER', True)
    age_hrs = config_dict.get('SR_MAX_RESTORE_AGE_HRS', 24)
    active  = len(_task_registry)

    msg = (
        f"<b>🗂️ Session Restore Status</b>\n\n"
        f"<b>Feature:</b> {'✅ Enabled' if enabled else '❌ Disabled'}\n"
        f"<b>Auto Retry:</b> {'✅ Yes' if auto_r else '❌ No'}\n"
        f"<b>Notify User:</b> {'✅ Yes' if notify else '❌ No'}\n"
        f"<b>Max Age:</b> {age_hrs} hours\n\n"
        f"<b>Tracked Tasks (this session):</b> {active}\n\n"
        f"<b>Restartable Types:</b>\n"
        + '\n'.join(f'  • <code>{t}</code>' for t in sorted(RESTARTABLE_TYPES))
    )
    await sendMessage(message, msg)


# ─────────────────────────────────────────
#  REGISTER HANDLERS
# ─────────────────────────────────────────

def add_handlers():
    bot.add_handler(
        MessageHandler(
            sessioninfo_command,
            filters=command(BotCommands.SessionInfoCommand) & CustomFilters.sudo,
        )
    )
    LOGGER.info("[SessionRestore] Handlers registered.")
