from re import search

from pyrogram.handlers import MessageHandler
from pyrogram.filters import create

from bot import bot, user_data
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.ext_utils.bot_utils import is_url, is_magnet
from bot.modules.mirror_leech import _mirror_leech
from bot.modules.ytdlp import _ytdl


def is_youtube_link(text: str) -> bool:
    if not text:
        return False
    return bool(search(r"(youtube\.com|youtu\.be)", text, flags=0))


async def auto_start_filter(_, __, message):
    if not message.from_user or message.from_user.is_bot:
        return False

    user_id = message.from_user.id
    if not user_data.get(user_id, {}).get("auto_start", False):
        return False

    text = (message.text or message.caption or "").strip()

    if text.startswith("/"):
        return False

    if message.media:
        return True

    if is_url(text) or is_magnet(text):
        return True

    return False


async def auto_start_func(client, message):
    text = (message.text or message.caption or "").strip()

    # media file auto leech
    if message.media:
        message.text = "/l"
        message.reply_to_message = message
        await _mirror_leech(client, message, isLeech=True)
        return

    # youtube auto leech
    if is_youtube_link(text):
        message.text = f"/yl {text}"
        await _ytdl(client, message, isLeech=True)
        return

    # magnet / normal link auto leech
    if is_url(text) or is_magnet(text):
        message.text = f"/l {text}"
        await _mirror_leech(client, message, isQbit=is_magnet(text), isLeech=True)
        return


bot.add_handler(
    MessageHandler(
        auto_start_func,
        filters=create(auto_start_filter)
        & CustomFilters.authorized_uset
        & ~CustomFilters.blacklisted,
    ),
    group=12,
)
