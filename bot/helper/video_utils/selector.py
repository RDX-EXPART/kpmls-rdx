from aiofiles.os import path as aiopath
from ast import literal_eval
from asyncio import Event, wait_for, wrap_future, gather
from functools import partial
from os import path as ospath
from PIL import Image
from re import match as re_match
from time import time

from pyrogram.filters import regex, user
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.types import Message, CallbackQuery

from bot import VID_MODE, VT_TIMEOUT, LOGGER, bot
from bot.helper.ext_utils.bot_utils import new_task, new_thread, sync_to_async
from bot.helper.ext_utils.fs_utils import clean_target
from bot.helper.utils import is_media, encode_dict, get_readable_time
from bot.helper.telegram_helper.button_maker import ButtonMaker
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.message_utils import send_message, edit_message, delete_message
from bot.core.config_manager import Config


# Pending text/media inputs for Video Tools menu.
# Key: (chat_id, user_id) -> {'obj': SelectMode, 'mode': str, 'is_sub': bool}
PENDING_VID_INPUTS = {}


class SelectMode():
    def __init__(self, mid, user_id, client, message, isLink=False):
        self._isLink = isLink
        self._time = time()
        self._reply = None
        self.is_rename = False
        self.mode = ''
        self.extra_data = {}
        self.newname = ''
        self.event = Event()
        self.message_event = Event()
        self.is_cancelled = False
        self.mid = mid
        self.user_id = user_id
        self.client = client
        self.message = message
        self.prefix = f"vidtool{mid}"
    
    @new_thread
    async def _event_handler(self):
        pfunc = partial(cb_vidtools, obj=self)
        handler = self.client.add_handler(CallbackQueryHandler(pfunc, filters=regex(f'^{self.prefix}') & user(self.user_id)), group=-1)
        try:
            await wait_for(self.event.wait(), timeout=VT_TIMEOUT)
        except Exception:
            self.mode = 'Task has been cancelled, time out!'
            self.is_cancelled = True
            self.event.set()
        finally:
            self.client.remove_handler(*handler)

    @new_thread
    async def message_event_handler(self, mode=''):
        # Register pending input in a module-level listener.
        # This is more reliable than adding/removing a temporary MessageHandler
        # from inside a callback query, especially on some Pyrogram bot setups
        # where free text after an inline button is not caught by the temp handler.
        self.message_event.clear()
        key = (self.message.chat.id, self.user_id)
        PENDING_VID_INPUTS[key] = {
            'obj': self,
            'mode': mode,
            'is_sub': mode == 'subfile',
            'created': time(),
        }
        try:
            await wait_for(self.message_event.wait(), timeout=VT_TIMEOUT / 2)
        except Exception:
            self.message_event.set()
        finally:
            pending = PENDING_VID_INPUTS.get(key)
            if pending and pending.get('obj') is self:
                PENDING_VID_INPUTS.pop(key, None)
            self.message_event.clear()

    async def _send_message(self, text: str, buttons):
        if not self._reply:
            self._reply = await send_message(self.message, text, buttons)
            return self._reply
        else:
            return await edit_message(self._reply, text, buttons)


    def _captions(self, mode: str=None):
        lines = ['╭── <b>Video Tools Settings</b>\n┊']
    
        if vidmode := VID_MODE.get(self.mode):
            lines.append(f'┊ Mode: <b>{vidmode}</b>')
    
        lines.append(f'┊ Name: <b>{self.newname or "Default"}</b>')
    
        if self.extra_data and self.mode == 'trim':
            lines.append(f'┊ Trim Duration: <b>{list(self.extra_data.values())}</b>')
    
        if self.mode in ('vid_sub', 'watermark'):
            hardsub = self.extra_data.get('hardsub')
            lines.append(f"┊ Hardsub Mode: <b>{'Enable' if hardsub else 'Disable'}</b>")
            if hardsub:
                lines.append(f"┊ Bold Style: <b>{'Enable' if self.extra_data.get('boldstyle') else 'Disable'}</b>")
                if fontname := self.extra_data.get('fontname') or Config.HARDSUB_FONT_NAME:
                    lines.append(f'┊ Font Name: <b>{fontname.replace("_", " ")}</b>')
                if fontsize := self.extra_data.get('fontsize') or Config.HARDSUB_FONT_SIZE:
                    lines.append(f'┊ Font Size: <b>{fontsize}</b>')
                if fontcolour := self.extra_data.get('fontcolour'):
                    lines.append(f'┊ Font Colour: <b>{fontcolour}</b>')
    
        if quality := self.extra_data.get('quality'):
            lines.append(f'┊ Quality: <b>{quality}</b>')
    
        if self.mode == 'watermark' and (wmsize := self.extra_data.get('wmsize')):
            lines.append(f'┊ WM Size: <b>{wmsize}</b>')
            if wmposition := self.extra_data.get('wmposition'):
                pos_dict = {
                    '5:5': 'Top Left',
                    'main_w-overlay_w-5:5': 'Top Right',
                    '5:main_h-overlay_h': 'Bottom Left',
                    'w-overlay_w-5:main_h-overlay_h-5': 'Bottom Right'
                }
                lines.append(f'┊ WM Position: <b>{pos_dict.get(wmposition, wmposition)}</b>')
            if popupwm := self.extra_data.get('popupwm'):
                lines.append(f'┊ Display: <b>{popupwm}x/20s</b>')
    
        if self.mode == 'subsync' and (typee := self.extra_data.get('type')):
            lines.append(f'┊ Sync Mode: <b>{typee.lstrip("sync_").title()}</b>')
    
        match mode:
            case 'encode':
                lines.append(f"┊ <b>Encode Mode</b>: {self.extra_data.get('encode_type')}")
            case 'rename':
                lines.append('\n<i>Send valid name with extension...</i>')
            case 'watermark':
                lines.append('\n<i>Send valid image to set as watermark...</i>')
            case 'subfile':
                lines.append('\n<i>Send valid subtitle (.ass or .srt) for hardsub...</i>')
            case 'wmsize':
                lines.append('\n<i>Choose watermark size</i>')
            case 'fontsize':
                lines.append(
                    '\n<i>Choose font size</i>\n'
                    '<b>Recommended:</b>\n'
                    '1080p: <b>21-26 </b>\n'
                    '720p: <b>16-21</b>\n'
                    '480p: <b>11-16</b>'
                )
            case 'trim':
                lines.append('\n<i>Send valid trim duration <b>hh:mm:ss hh:mm:ss</b></i>')
    
        timeout = get_readable_time(VT_TIMEOUT - (time() - self._time))
        lines.append(f'╰──<i>Time Out: {timeout}</i>')
    
        return '\n'.join(lines)
        
    async def list_buttons(self, mode: str=''):
        bMaker, bnum = ButtonMaker(), 2
        if not mode:
            vid_modes = dict(list(VID_MODE.items())[4:]) if self._isLink else VID_MODE
            for key, value in vid_modes.items():
                if self.mode == key:
                    bMaker.ibutton(f"✓ {value}", f'{self.prefix} {key}')
                else:
                    bMaker.ibutton(value, f'{self.prefix} {key}')
            
            bMaker.ibutton(f'{"✓ " if self.newname else ""}Rename', f'{self.prefix} rename', position='header')
            bMaker.ibutton('Cancel', f'{self.prefix} cancel', 'footer')
            if self.mode:
                bMaker.ibutton('Start', f'{self.prefix} done', 'footer')
            if self.mode in ('vid_sub', 'watermark') and await CustomFilters.sudo('', self.message):
                hardsub = self.extra_data.get('hardsub')
                bMaker.ibutton(f"{'✓ ' if hardsub else ''}Hardsub", f'{self.prefix} hardsub', 'header')
                if hardsub:
                    if self.mode == 'watermark':
                        bMaker.ibutton(f"{'✓ ' if await aiopath.exists(self.extra_data.get('subfile', '')) else ''}Sub File", f'{self.prefix} subfile', 'header')
                    bMaker.ibutton('Font Style', f'{self.prefix} fontstyle', 'header')

            if self.mode in ('compress', 'watermark') or self.extra_data.get('hardsub'):
                bMaker.ibutton('Quality', f'{self.prefix} quality', 'header')
            if self.mode == 'watermark':
                bMaker.ibutton('Popup', f'{self.prefix} popupwm', 'header')
        else:
            def _buttons_style(name=True, size=True, colour=True, position='header', cb='fontstyle'):
                if name:
                    bMaker.ibutton('Font Name', f'{self.prefix} fontstyle fontname', position)
                if size:
                    bMaker.ibutton('Font Size', f'{self.prefix} fontstyle fontsize', position)
                if colour:
                    bMaker.ibutton('Font Colour', f'{self.prefix} fontstyle fontcolour', position)
                bMaker.ibutton('<<', f'{self.prefix} {cb}', 'footer')
                bMaker.ibutton('Done', f'{self.prefix} done', 'footer')
            
            match mode:
                case 'subsync':
                    bMaker.ibutton('Manual', f'{self.prefix} sync_manual')
                    bMaker.ibutton('Auto', f'{self.prefix} sync_auto')
                case 'quality':
                    bnum = 3
                    [bMaker.ibutton(f"{'✓ ' if self.extra_data.get('quality') == key else ''}{key}", f'{self.prefix} quality {key}') for key in ['1080p', '720p', '540p', '480p', '360p']]
                    bMaker.ibutton('<<', f'{self.prefix} back', 'footer')
                    bMaker.ibutton('Done', f'{self.prefix} done', 'footer')
                case 'popupwm':
                    bnum, popupwm = 5, self.extra_data.get('popupwm', 0)
                    if popupwm:
                        bMaker.ibutton('Reset', f'{self.prefix} popupwm 0', 'header')
                    [bMaker.ibutton(f"{'✓ ' if popupwm == key else ''}{key}", f'{self.prefix} popupwm {key}') for key in range(2, 21, 2)]
                    bMaker.ibutton('<<', f'{self.prefix} back', 'footer')
                    bMaker.ibutton('Done', f'{self.prefix} done', 'footer')
                case 'wmsize':
                    bnum = 3
                    [bMaker.ibutton(str(btn), f'{self.prefix} wmsize {btn}') for btn in [5, 10, 15, 20, 25, 30]]
                case 'fontstyle':
                    bnum = 3
                    _buttons_style(position=None, cb='back')
                    bMaker.ibutton(f"{'✓ ' if self.extra_data.get('boldstyle') else ''}Bold Style", f"{self.prefix} fontstyle boldstyle {self.extra_data.get('boldstyle', False)}", 'header')
                case 'fontname':
                    _buttons_style(name=False)
                    [bMaker.ibutton(f"{'✓ ' if btn == self.extra_data.get('fontname') else ''}{btn.replace('_', ' ')}", f'{self.prefix} fontstyle fontname {btn}')
                     for btn in ['Arial', 'Impact', 'Verdana', 'Consolas', 'DejaVu_Sans', 'Comic_Sans_MS', 'Simple_Day_Mistu']]
                case 'fontsize':
                    bnum = 5
                    _buttons_style(size=False)
                    [bMaker.ibutton(f"{'✓ ' if str(btn) == self.extra_data.get('fontsize') else ''}{btn}", f'{self.prefix} fontstyle fontsize {btn}') for btn in range(11, 31)]
                case 'fontcolour':
                    bnum = 3
                    _buttons_style(colour=False)
                    colours = [('Red', '0000ff'), ('Green', '00ff00'), ('Blue', 'ff0000'), ('Yellow', '00ffff'), ('Orange', '0054ff'), ('Purple', '005aff'),
                               ('Soft Red', 'd470ff'), ('Soft Green', '80ff80'), ('Soft Blue', 'ffb84d'), ('Soft Yellow', '80ffff')]
                    [bMaker.ibutton(f"{'✓ ' if hexcolour == self.extra_data.get('fontcolour') else ''}{btn}", f'{self.prefix} fontstyle fontcolour {hexcolour}') for btn, hexcolour in colours]
                case 'wmposition':
                    bMaker.ibutton('Top Left', f'{self.prefix} wmposition 5:5')
                    bMaker.ibutton('Top Right', f'{self.prefix} wmposition main_w-overlay_w-5:5')
                    bMaker.ibutton('Bottom Left', f'{self.prefix} wmposition 5:main_h-overlay_h')
                    bMaker.ibutton('Bottom Right', f'{self.prefix} wmposition w-overlay_w-5:main_h-overlay_h-5')
                case 'encode':
                    encode_type = self.extra_data.get('encode_type', '')
                    for qual in encode_dict.keys():
                        is_tick = ' ✓' if qual==encode_type else ''
                        bMaker.ibutton(qual+is_tick, f'{self.prefix} encostart {qual}')
                    bMaker.ibutton('<< Back', f'{self.prefix} back', 'footer')
                    bMaker.ibutton('Done', f'{self.prefix} done', 'footer')
                    
                case _:
                    bMaker.ibutton('<<', f'{self.prefix} back', 'footer')
        return await self._send_message(self._captions(mode), bMaker.build(bnum, 3))

    async def get_buttons(self):
        future = self._event_handler()
        await gather(self.list_buttons(), wrap_future(future))
        if self.is_cancelled:
            await edit_message(self._reply, self.mode)
            return
        await delete_message(self._reply)
        return [self.mode, self.newname, self.extra_data]


async def message_handler(_, message: Message, obj: SelectMode, is_sub=False):
    data = None

    # Accept input only from the same chat and same user that opened the menu.
    if message.chat.id != obj.message.chat.id:
        return
    if not message.from_user or message.from_user.id != obj.user_id:
        return

    if obj.is_rename and message.text:
        new_name = message.text.strip().replace('/', '').replace('\\', '')
        # Require extension at the end: Movie 720p.mkv
        if not new_name or not re_match(r'^.+\.[A-Za-z0-9]{1,8}$', new_name):
            await send_message(message, 'Invalid name! Send name with extension, example: <code>Movie 720p.mkv</code>')
            return
        obj.newname = new_name
        obj.is_rename = False
    elif obj.mode == 'watermark' and (media := is_media(message)):
        if is_sub:
            if message.document and not media.file_name.lower().endswith(('.ass', '.srt')):
                await send_message(message, 'Only .ass or .srt allowed!')
                return
            obj.extra_data['subfile'] = await message.download(ospath.join('watermark', media.file_id))
        else:
            if message.document and 'image' not in getattr(media, 'mime_type', 'None'):
                await send_message(message, 'Only image document allowed!')
                return
            fpath = await message.download(ospath.join('watermark', media.file_id))
            await sync_to_async(Image.open(fpath).convert('RGBA').save, ospath.join('watermark', f'{obj.mid}.png'), 'PNG')
            await clean_target(fpath)
            data = 'wmsize'
            
    elif obj.mode == 'trim' and message.text:
        if match := re_match(r'(\d{2}:\d{2}:\d{2})\s(\d{2}:\d{2}:\d{2})', message.text.strip()):
            obj.extra_data.update({'start_time': match.group(1), 'end_time': match.group(2)})
        else:
            await send_message(message, 'Invalid trim duration format!')
            return
    obj.message_event.set()
    await gather(obj.list_buttons(data), delete_message(message))


async def vidtools_global_message_handler(client, message: Message):
    """Catch rename/trim/watermark/subtitle inputs for active Video Tools menus."""
    if not message.chat or not message.from_user:
        return
    key = (message.chat.id, message.from_user.id)
    pending = PENDING_VID_INPUTS.get(key)
    if not pending:
        return
    obj = pending.get('obj')
    if not obj or obj.message_event.is_set():
        return
    await message_handler(client, message, obj=obj, is_sub=pending.get('is_sub', False))


# Register one permanent listener. Temporary listeners were missing normal text
# inputs on some deployments, causing Rename/Trim values not to save.
try:
    bot.add_handler(MessageHandler(vidtools_global_message_handler), group=-1000)
except Exception:
    LOGGER.error('Failed to register Video Tools input handler', exc_info=True)


@new_task
async def cb_vidtools(_, query: CallbackQuery, obj: SelectMode):
    data = query.data.split()
    if data[1] in Config.DISABLE_VIDTOOLS:
        await query.answer(f'{VID_MODE[data[1]]} has been disabled!', True)
        return
    
    await query.answer()
    # Do not block Rename even if a previous state is active.
    if data[1] == obj.mode and data[1] not in ('encode', 'rename'):
        return
    match data[1]:
        case 'done':
            obj.event.set()
        case 'back':
            if obj.message_event:
                obj.message_event.set()
            await obj.list_buttons()
        case 'cancel':
            obj.mode = 'Task has been cancelled!'
            obj.is_cancelled = True
            obj.event.set()
        case 'quality' | 'popupwm' as value:
            if len(data) == 3:
                obj.extra_data[value] = data[2] if value == 'quality' else int(data[2])
            await obj.list_buttons(value)
        case 'hardsub':
            hmode = not bool(obj.extra_data.get('hardsub'))
            if not hmode and obj.mode == 'vid_sub':
                obj.extra_data.clear()
            obj.extra_data['hardsub'] = hmode
            await obj.list_buttons()
        case 'subfile':
            future = obj.message_event_handler('subfile')
            await gather(obj.list_buttons('subfile'), wrap_future(future))
        case 'fontstyle':
            mode = 'fontstyle'
            if len(data) > 2:
                mode = data[2]
                is_bold = mode == 'boldstyle'
                if len(data) == 4:
                    if not is_bold and obj.extra_data.get(mode) == data[3]:
                        return
                    obj.extra_data[mode] = not literal_eval(data[3]) if is_bold else data[3]
                if is_bold:
                    mode = 'fontstyle'
            await obj.list_buttons(mode)
        case 'sync_manual' | 'sync_auto' as value:
            obj.extra_data['type'] = value
            await obj.list_buttons()
        case 'wmsize' | 'wmposition' as value:
            obj.extra_data[value] = data[2]
            await obj.list_buttons('wmposition' if value == 'wmsize' else None)
        case 'encostart':
            obj.extra_data['encode_type'] = data[-1]
            await obj.list_buttons('encode')
        case value:
            if value == 'rename':
                obj.is_rename = True
            else:
                obj.mode = value
                obj.extra_data.clear()
            if value in ('watermark', 'rename', 'trim', 'encode'):
                future = obj.message_event_handler(value)
                await gather(obj.list_buttons(value), wrap_future(future))
                return
            
            await obj.list_buttons('subsync' if value == 'subsync' else '')
