#!/usr/bin/env python3
"""
SESSION RESTORE — tasks_listener.py integration guide
======================================================

tasks_listener.py এর MirrorLeechListener class এ নিচের changes করতে হবে।

STEP 1: Import add করুন (file এর top এ):
─────────────────────────────────────────
from bot.modules.session_restore import sr_save_task, sr_remove_task
from bot.modules.inline_task_control import register_retry, unregister_retry

STEP 2: on_download_start() বা সমতুল্য method এ save করুন:
────────────────────────────────────────────────────────────
# task শুরু হওয়ার সময় (download শুরুতে):

await sr_save_task(
    task_id      = str(self.uid),           # message id / unique id
    user_id      = self.user_id,
    chat_id      = self.message.chat.id,
    command_text = self.message.text or '', # original command
    task_type    = 'leech' if self.isLeech else 'mirror',
)

# Inline Retry support:
register_retry(
    gid          = gid,                     # download gid
    chat_id      = self.message.chat.id,
    user_id      = self.user_id,
    command_text = self.message.text or '',
)

STEP 3: on_download_complete() / on_upload_complete() এ remove করুন:
──────────────────────────────────────────────────────────────────────
await sr_remove_task(str(self.uid))
unregister_retry(gid)

STEP 4: on_download_error() / on_upload_error() এ remove করুন:
────────────────────────────────────────────────────────────────
await sr_remove_task(str(self.uid))
unregister_retry(gid)


INLINE TASK BUTTONS — get_readable_message() integration
=========================================================

bot/helper/ext_utils/bot_utils.py এর get_readable_message() function এ:

STEP 1: Import (top এ):
─────────────────────────
from bot.modules.inline_task_control import build_task_buttons

STEP 2: প্রতি task এর message এর নিচে button add করুন।
        নিচের code টা msg এর শেষে add করুন (Stop line এর পরে):

try:
    task_buttons = build_task_buttons(download.gid(), uid)
    # এই markup টা individual message এ use করুন।
    # Note: status page এ overall button ব্যবহার করা হয়,
    # তাই individual task control এর জন্য আলাদা message পাঠাতে হবে।
    # অথবা নিচের মতো GID টা status message এ mention করুন:
    msg += f"<b>╰ Controls » Reply to task or use GID buttons below</b>\n\n"
except Exception:
    pass


AUTO THEME — get_readable_message() integration  
================================================

bot/helper/ext_utils/bot_utils.py এর get_readable_message() function এ:

STEP 1: Import:
───────────────
from bot.modules.auto_theme import get_theme_icon, get_theme_bar

STEP 2: progress bar এবং emoji গুলো replace করুন:
────────────────────────────────────────────────────
# পুরনো:
# bar = get_progress_bar_dots(download.progress(), length=12)

# নতুন (auto theme aware):
try:
    from bot.modules.auto_theme import get_theme_bar, get_theme_icon
    bar        = get_theme_bar(download.progress(), length=12)
    _dl_emoji  = get_theme_icon('dl_icon')
    _ul_emoji  = get_theme_icon('ul_icon')
    _spd_emoji = get_theme_icon('spd_icon')
    _size_emoji= get_theme_icon('size_icon')
    _time_emoji= get_theme_icon('time_icon')
    _seed_emoji= get_theme_icon('seed_icon')
    _wait_emoji= get_theme_icon('wait_icon')
except Exception:
    bar = get_progress_bar_dots(download.progress(), length=12)
    _dl_emoji = '📥'; _ul_emoji = '📤'
    _spd_emoji = '⚡'; _size_emoji = '📦'
    _time_emoji = '⏰'; _seed_emoji = '🌱'; _wait_emoji = '⏸️'
