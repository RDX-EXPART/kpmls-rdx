from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from bot.core.config_manager import BinConfig


class ButtonMaker:
    def __init__(self):
        self._buttons = []
        self._header_button = []
        self._footer_button = []
        self._last_button = []

    def _btn(self, key, *, url=None, data=None, emoji_id=None, style=None):
        kwargs = {"text": key}

        if url:
            kwargs["url"] = url
        if data:
            kwargs["callback_data"] = data

        if emoji_id is not None and BinConfig.PYRO_NAME == 'kurigram':
            kwargs["icon_custom_emoji_id"] = emoji_id

        if style is not None and BinConfig.PYRO_NAME == 'kurigram':
            kwargs["style"] = style

        return InlineKeyboardButton(**kwargs)

    def ubutton(self, key, link, position=None, emoji_id=None, style=None):
        btn = self._btn(key, url=link, emoji_id=emoji_id, style=style)

        match position:
            case 'header':
                self._header_button.append(btn)
            case 'footer':
                self._footer_button.append(btn)
            case 'last':
                self._last_button.append(btn)
            case _:
                self._buttons.append(btn)

    def ibutton(self, key, data, position=None, emoji_id=None, style=None):
        btn = self._btn(key, data=data, emoji_id=emoji_id, style=style)

        match position:
            case 'header':
                self._header_button.append(btn)
            case 'footer':
                self._footer_button.append(btn)
            case 'last':
                self._last_button.append(btn)
            case _:
                self._buttons.append(btn)

    def build(self, b_cols=None, h_cols=None, f_cols=None):
        total = len(self._buttons) + len(self._footer_button) + len(self._last_button)

        if b_cols is None:
            b_cols = 6 if total >= 6 else max(1, total)

        if h_cols is None:
            h_cols = min(8, max(1, len(self._header_button)))

        if f_cols is None:
            f_cols = b_cols

        menu = [self._buttons[i:i + b_cols] for i in range(0, len(self._buttons), b_cols)]

        if self._header_button:
            header = [self._header_button[i:i + h_cols] for i in range(0, len(self._header_button), h_cols)]
            menu = header + menu

        if self._footer_button:
            footer = [self._footer_button[i:i + f_cols] for i in range(0, len(self._footer_button), f_cols)]
            menu.extend(footer)

        if self._last_button:
            menu.append(self._last_button)

        return InlineKeyboardMarkup(menu) if menu else None