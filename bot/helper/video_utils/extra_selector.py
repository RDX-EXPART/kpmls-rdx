from ast import literal_eval
from asyncio import Event, wait_for, wrap_future, gather, TimeoutError
from functools import partial
from time import time
from natsort import natsorted
from os import path as ospath
from aiofiles import open as aiopen

from pyrogram.filters import regex, user, text, user, incoming
from pyrogram.handlers import CallbackQueryHandler, MessageHandler
from pyrogram.types import CallbackQuery

from bot import VID_MODE, VT_TIMEOUT, LOGGER
from bot.helper.ext_utils.bot_utils import new_thread
from bot.helper.utils import get_readable_file_size, get_readable_time
from bot.helper.telegram_helper.button_maker import ButtonMaker
from bot.helper.telegram_helper.message_utils import send_message, edit_message, delete_message
from bot.helper.ext_utils.fs_utils import get_path_size
from bot.helper.utils.gk_utils import cb_merge_text


class ExtraSelect:
    def __init__(self, executor):
        self._listener = executor.listener
        self._time = time()
        self._reply = None
        self.executor = executor
        self.event = Event()
        self.is_cancelled = False
        self.extension: list[str] = [None, None, 'mkv']
        self.status = ''
        self.prefix = f'extra{executor.listener.mid}'
    
    
    @new_thread
    async def _event_handler(self):
        pfunc = partial(cb_extra, obj=self)
        handler = self._listener.client.add_handler(CallbackQueryHandler(pfunc, filters=regex(f'^{self.prefix}') & user(self._listener.user_id)), group=-1)
        try:
            await wait_for(self.event.wait(), timeout=VT_TIMEOUT)
        except Exception:
            self.event.set()
        finally:
            self._listener.client.remove_handler(*handler)

    async def update_message(self, text: str, buttons):
        if not self._reply:
            self._reply = await send_message(self._listener.message, text, buttons)
        else:
            await edit_message(self._reply, text, buttons)
    
    async def merge_entry(self, file_list: list):
        sorted_files = natsorted(file_list)
    
        self.executor.data = {
            'files': sorted_files,
            'instructions': None,
        }
    
        total_size = sum([await get_path_size(f) for f in sorted_files])
        folder_name = ospath.basename(ospath.dirname(sorted_files[0]))
    
        msg = (
            f'<b>MERGE PANEL ~ {self._listener.tag}</b>\n\n'
            f'<b>Folder:</b> <code>{folder_name}</code>\n'
            f'<b>Total Files:</b> {len(sorted_files)}\n'
            f'<b>Total Size:</b> {get_readable_file_size(total_size)}\n\n'
            f'<i>Choose how to proceed.\n'
            f'Auto-merging on timeout.</i>\n\n'
            f'<i>Time Out: {get_readable_time(VT_TIMEOUT)}</i>'
        )
    
        bMaker = ButtonMaker()
        bMaker.ibutton('📜 Send Instructions', f'{self.prefix} merge_start')
        bMaker.ibutton('⚡ Skip', f'{self.prefix} merge_skip')
        #bMaker.ibutton('❌ Cancel', f'{self.prefix} cancel', 'footer')
    
        self._reply = await send_message(self._listener.message, msg, bMaker.build())
    
        # ✅ SINGLE EVENT
        self.event = Event()
    
        handler = self._listener.client.add_handler(
            CallbackQueryHandler(
                partial(cb_extra, obj=self),
                filters=regex(f'^{self.prefix}') & user(self._listener.user_id)
            ),
            group=-1
        )
    
        try:
            await wait_for(self.event.wait(), timeout=VT_TIMEOUT)
    
        except TimeoutError:
            files = self.executor.data.get('files') or []
            if files and not self.executor.data.get('instructions'):
                self.executor.data['instructions'] = [{
                    'files': files,
                    'name': self.executor.name or ospath.basename(files[0]),
                    'copy_only': False,
                }]
    
        finally:
            self._listener.client.remove_handler(*handler)
    
            try:
                if self._reply:
                    await delete_message(self._reply)
                    self._reply = None
            except:
                pass
    
        self.data = self.executor.data
    
    async def merge_select(self, file_list: list):
        sorted_files = natsorted(file_list)
    
        # DO NOT reset event
        self.executor.data['files'] = sorted_files
    
        file_lines = []
        for i, f in enumerate(sorted_files, 1):
            size = await get_path_size(f)
            file_lines.append(
                f'<b>{i}.</b> <code>{ospath.basename(f)}</code>\n'
                f'    <i>{get_readable_file_size(size)}</i>'
            )
    
        msg = (
            f'<b>MERGE SELECTOR ~ {self._listener.tag}</b>\n\n'
            f'<code>COUNT|NAME.mkv</code>\n\n'
            f'<i>Send instructions or /skip</i>\n\n'
            + '\n'.join(file_lines)
        )
    
        bMaker = ButtonMaker()
        bMaker.ibutton('❌ Cancel', f'{self.prefix} cancel', 'footer')
    
        if self._reply:
            try:
                await delete_message(self._reply)
            except:
                pass
    
        self._reply = await send_message(
            self._listener.message, msg, bMaker.build()
        )
    
        # ✅ ONLY attach handler, no wait
        pfunc = partial(cb_merge_text, obj=self)
    
        self._handler = self._listener.client.add_handler(
            MessageHandler(
                pfunc,
                filters=incoming & user(self._listener.user_id)
            ),
            group=-1
        )
        
    async def hard_sub_select(self, streams: dict = None):
        """HardSub selector - select subtitle to burn into video"""
        bMaker = ButtonMaker()
        
        # Initialize data structure if not exists
        if not self.executor.data:
            self.executor.data = {}
        
        # Set defaults
        self.executor.data.setdefault('stream', {})
        self.executor.data.setdefault('subtitle_streams', [])
        self.executor.data.setdefault('selected_sub', None)
        self.executor.data.setdefault('selected_lang', None)
        self.executor.data.setdefault('current_file', self.executor.name)
        self.executor.data.setdefault('file_index', 0)
        self.executor.data.setdefault('total_files', 0)
        
        # Collect subtitle streams only if streams provided
        if streams:
            # Clear previous streams
            self.executor.data['stream'] = {}
            self.executor.data['subtitle_streams'] = []
            
            for stream in streams:
                indexmap = stream.get('index')
                codec_name = stream.get('codec_name')
                codec_type = stream.get('codec_type')
                lang = stream.get('tags', {}).get('language', str(indexmap))
                
                if codec_type == 'subtitle':
                    self.executor.data['stream'][indexmap] = {
                        'info': f'Subtitle ~ {lang.upper()} ({codec_name})',
                        'name': codec_name,
                        'map': indexmap,
                        'type': codec_type,
                        'lang': lang
                    }
                    self.executor.data['subtitle_streams'].append(indexmap)
        
        ddict = self.executor.data
        subtitle_count = len(ddict.get('subtitle_streams', []))
        
        # Check if we have subtitles
        if subtitle_count == 0:
            text = (
                f'<b>HARDSUB ERROR ~ {self._listener.tag}</b>\n'
                f'<code>{self.executor.name}</code>\n\n'
                f'⚠️ No subtitle streams found in video!'
            )
            bMaker.ibutton('❌ Cancel', f'{self.prefix} cancel')
            await self.update_message(text, bMaker.build())
            return
        
        # Build UI
        selected_sub = ddict.get('selected_sub')
        file_index = ddict.get('file_index', 0)
        total_files = ddict.get('total_files', 0)
        current_file = ddict.get('current_file', self.executor.name)
        
        # Show file context
        if total_files > 1:
            if file_index == 0:
                folder_name = ospath.basename(ospath.dirname(current_file))
                context = f'<b>Folder:</b> {folder_name}\n'
            else:
                context = f'<b>File {file_index + 1}/{total_files}:</b>\n<code>{ospath.basename(current_file)}</code>\n'
        else:
            context = f'<code>{ospath.basename(current_file)}</code>\n'
        
        text = (
            f'<b>HARDSUB SETTINGS ~ {self._listener.tag}</b>\n'
            f'{context}'
            f'<b>┌ </b>File Size: <b>{get_readable_file_size(self.executor.size)}</b>\n'
            f'<b>└ </b>Subtitle Streams: <b>{subtitle_count}</b>\n\n'
        )
        
        if selected_sub is not None and selected_sub in ddict.get('stream', {}):
            selected_info = ddict['stream'][selected_sub]['info']
            text += f'<b>Selected:</b> {selected_info}\n\n'
        
        text += '🔹 <b>Select subtitle to burn into video:</b>\n\n'
        
        # Build buttons for subtitle streams
        for idx in ddict.get('subtitle_streams', []):
            stream_info = ddict['stream'][idx]
            button_text = stream_info['info']
            
            if idx == selected_sub:
                button_text = f'✅ {button_text}'
            
            bMaker.ibutton(button_text, f'{self.prefix} hard_sub {idx}')
        
        # Control buttons
        if selected_sub is not None:
            bMaker.ibutton('✅ Continue', f'{self.prefix} hard_sub continue', 'footer')
        
        bMaker.ibutton('❌ Cancel', f'{self.prefix} cancel', 'footer')
        
        text += f'\n<i>Time Out: {get_readable_time(VT_TIMEOUT - (time()-self._time))}</i>'
        await self.update_message(text, bMaker.build(2))


    async def advconvert_select(self, streams: dict = None):
        """Advanced conversion selector with multiple stream types"""
        bMaker = ButtonMaker()
        
        if not self.executor.data:
            self.executor.data = {
                'stream': {},
                'video_streams': [],
                'audio_streams': [],
                'subtitle_streams': [],
                'selected_types': [],  # ['video', 'audio', 'subtitle']
                'video_settings': {},
                'audio_settings': {},
                'subtitle_settings': {},
                'stage': 'select_type',  # stages: select_type, configure, review, waiting_input
                'waiting_for': None,  # Which parameter waiting for user input
                'hardsub_stream': None
            }
            
            # Collect all streams from video
            if streams:
                for stream in streams:
                    indexmap = stream.get('index')
                    codec_name = stream.get('codec_name')
                    codec_type = stream.get('codec_type')
                    lang = stream.get('tags', {}).get('language', str(indexmap))
                    
                    if codec_type == 'video':
                        width = stream.get('width', 0)
                        height = stream.get('height', 0)
                        fps = stream.get('r_frame_rate', '').split('/')[0] if stream.get('r_frame_rate') else 'N/A'
                        self.executor.data['stream'][indexmap] = {
                            'info': f'Video ~ {width}x{height} ({codec_name}) {fps}fps',
                            'name': codec_name,
                            'map': indexmap,
                            'type': codec_type,
                            'width': width,
                            'height': height
                        }
                        self.executor.data['video_streams'].append(indexmap)
                    
                    elif codec_type == 'audio':
                        channels = stream.get('channels', 2)
                        ch_layout = f'{channels}ch' if channels else ''
                        self.executor.data['stream'][indexmap] = {
                            'info': f'Audio ~ {lang.upper()} ({codec_name}) {ch_layout}',
                            'name': codec_name,
                            'map': indexmap,
                            'type': codec_type,
                            'lang': lang,
                            'channels': channels
                        }
                        self.executor.data['audio_streams'].append(indexmap)
                    
                    elif codec_type == 'subtitle':
                        self.executor.data['stream'][indexmap] = {
                            'info': f'Subtitle ~ {lang.upper()} ({codec_name})',
                            'name': codec_name,
                            'map': indexmap,
                            'type': codec_type,
                            'lang': lang
                        }
                        self.executor.data['subtitle_streams'].append(indexmap)
        
        ddict = self.executor.data
        stage = ddict.get('stage', 'select_type')
        
        # Stage 1: Select stream types to convert
        if stage == 'select_type':
            await self._convert_type_selection(ddict, bMaker)
        
        # Stage 2: Configure settings for selected types
        elif stage == 'configure':
            await self._convert_configuration(ddict, bMaker)
        
        # Stage 3: Review all settings before processing
        elif stage == 'review':
            await self._convert_review(ddict, bMaker)
        
        # Stage 4: Waiting for user input
        elif stage == 'waiting_input':
            await self._convert_waiting_input(ddict, bMaker)
    
    async def _convert_type_selection(self, ddict, bMaker):
        """Stage 1: Select which stream types to convert"""
        selected_types = ddict.get('selected_types', [])
        
        text = (
            f'<b>ADVANCED CONVERT ~ {self._listener.tag}</b>\n'
            f'<code>{self.executor.name}</code>\n'
            f'<b>┌ </b>File Size: <b>{get_readable_file_size(self.executor.size)}</b>\n'
            f'<b>├ </b>Video Streams: <b>{len(ddict["video_streams"])}</b>\n'
            f'<b>├ </b>Audio Streams: <b>{len(ddict["audio_streams"])}</b>\n'
            f'<b>└ </b>Subtitle Streams: <b>{len(ddict["subtitle_streams"])}</b>\n\n'
            f'🔹 <b>Step 1:</b> Select stream types to convert\n'
            f'   (You can select multiple)\n\n'
        )
        
        if selected_types:
            text += '<b>Selected Types:</b>\n'
            for stype in selected_types:
                text += f'✓ {stype.title()}\n'
            text += '\n'
        
        text += '<b>Available Stream Types:</b>\n'
        
        # Video button
        if ddict['video_streams']:
            video_text = '✓ 🎬 Video' if 'video' in selected_types else '🎬 Video'
            bMaker.ibutton(video_text, f'{self.prefix} convert_type video')
        
        # Audio button
        if ddict['audio_streams']:
            audio_text = '✓ 🎵 Audio' if 'audio' in selected_types else '🎵 Audio'
            bMaker.ibutton(audio_text, f'{self.prefix} convert_type audio')
        
        # Subtitle button
        if ddict['subtitle_streams']:
            sub_text = '✓ 📝 Subtitle' if 'subtitle' in selected_types else '📝 Subtitle'
            bMaker.ibutton(sub_text, f'{self.prefix} convert_type subtitle')
        
        # Control buttons
        if selected_types:
            bMaker.ibutton('➡️ Next', f'{self.prefix} convert_type next', 'footer')
        
        bMaker.ibutton('❌ Cancel', f'{self.prefix} cancel', 'footer')
        
        text += f'\n<i>Time Out: {get_readable_time(VT_TIMEOUT - (time()-self._time))}</i>'
        await self.update_message(text, bMaker.build(2))
    
    async def _convert_configuration(self, ddict, bMaker):
        """Stage 2: Configure conversion settings"""
        selected_types = ddict.get('selected_types', [])
        current_config = ddict.get('current_config_type', selected_types[0] if selected_types else None)
        
        text = (
            f'<b>ADVANCED CONVERT ~ {self._listener.tag}</b>\n'
            f'<code>{self.executor.name}</code>\n\n'
            f'🔹 <b>Step 2:</b> Configure {current_config.title() if current_config else ""} Settings\n\n'
        )
        
        if current_config == 'video':
            await self._video_configuration(ddict, bMaker, text)
        elif current_config == 'audio':
            await self._audio_configuration(ddict, bMaker, text)
        elif current_config == 'subtitle':
            await self._subtitle_configuration(ddict, bMaker, text)
    
    async def _video_configuration(self, ddict, bMaker, text):
        """Video conversion configuration"""
        vsettings = ddict.get('video_settings', {})
        
        # Show current settings
        text += '<b>Current Video Settings:</b>\n'
        text += f"CRF: <code>{vsettings.get('crf', 'Not Set')}</code>\n"
        text += f"Codec: <code>{vsettings.get('codec', 'Not Set')}</code>\n"
        text += f"Preset: <code>{vsettings.get('preset', 'Not Set')}</code>\n"
        text += f"Resolution: <code>{vsettings.get('resolution', 'Not Set')}</code>\n"
        text += f"FPS: <code>{vsettings.get('fps', 'Not Set')}</code>\n"
        text += f"Bitrate: <code>{vsettings.get('bitrate', 'Not Set')}</code>\n"
        text += f"Pixel Format: <code>{vsettings.get('pix_fmt', 'Not Set')}</code>\n"
        text += f"Extension: <code>{vsettings.get('extension', 'Not Set')}</code>\n\n"
        
        # Preset buttons
        bMaker.ibutton('🎬 High Quality', f'{self.prefix} convert_video preset_hq', 'header')
        bMaker.ibutton('⚡ Fast Encode', f'{self.prefix} convert_video preset_fast', 'header')
        bMaker.ibutton('💾 Small Size', f'{self.prefix} convert_video preset_small', 'header')
        bMaker.ibutton('📱 Mobile', f'{self.prefix} convert_video preset_mobile', 'header')
        
        # Individual settings
        bMaker.ibutton('CRF (0-51)', f'{self.prefix} convert_video crf')
        bMaker.ibutton('Codec', f'{self.prefix} convert_video codec')
        bMaker.ibutton('Preset', f'{self.prefix} convert_video preset')
        bMaker.ibutton('Resolution', f'{self.prefix} convert_video resolution')
        bMaker.ibutton('FPS', f'{self.prefix} convert_video fps')
        bMaker.ibutton('Bitrate', f'{self.prefix} convert_video bitrate')
        bMaker.ibutton('Pixel Format', f'{self.prefix} convert_video pix_fmt')
        bMaker.ibutton('Extension', f'{self.prefix} convert_video extension')
        bMaker.ibutton('🔧 Custom FFmpeg', f'{self.prefix} convert_video custom', 'footer')
        
        # Navigation
        if len(ddict['selected_types']) > 1:
            bMaker.ibutton('➡️ Next Type', f'{self.prefix} convert_config next', 'footer')
        else:
            bMaker.ibutton('➡️ Review', f'{self.prefix} convert_config review', 'footer')
        
        bMaker.ibutton('↩️ Back', f'{self.prefix} convert_config back', 'footer')
        bMaker.ibutton('❌ Cancel', f'{self.prefix} cancel', 'footer')
        
        text += f'<i>Time Out: {get_readable_time(VT_TIMEOUT - (time()-self._time))}</i>'
        await self.update_message(text, bMaker.build(3))
    
    async def _audio_configuration(self, ddict, bMaker, text):
        """Audio conversion configuration"""
        asettings = ddict.get('audio_settings', {})
        audio_streams = ddict['audio_streams']
        
        # Show current settings
        text += '<b>Current Audio Settings:</b>\n'
        text += f"Apply To: <code>{asettings.get('apply_to', 'All Streams')}</code>\n"
        text += f"Codec: <code>{asettings.get('codec', 'Not Set')}</code>\n"
        text += f"Bitrate: <code>{asettings.get('bitrate', 'Not Set')}</code>\n"
        text += f"Sample Rate: <code>{asettings.get('sample_rate', 'Not Set')}</code>\n"
        text += f"Channels: <code>{asettings.get('channels', 'Not Set')}</code>\n"
        text += f"Extension: <code>{asettings.get('extension', 'Not Set')}</code>\n\n"
        
        # Stream selection (if multiple audio streams)
        if len(audio_streams) > 1:
            text += '<b>Select Streams to Convert:</b>\n'
            bMaker.ibutton('✓ All Streams' if asettings.get('apply_to') == 'all' else 'All Streams', 
                          f'{self.prefix} convert_audio apply_all', 'header')
            bMaker.ibutton('Select Specific', f'{self.prefix} convert_audio select_streams', 'header')
        
        # Preset buttons
        bMaker.ibutton('🎵 AAC 192k', f'{self.prefix} convert_audio preset_aac192', 'header')
        bMaker.ibutton('💿 AAC 320k', f'{self.prefix} convert_audio preset_aac320', 'header')
        bMaker.ibutton('📻 MP3 320k', f'{self.prefix} convert_audio preset_mp3', 'header')
        bMaker.ibutton('🎼 FLAC', f'{self.prefix} convert_audio preset_flac', 'header')
        
        # Individual settings
        bMaker.ibutton('Codec', f'{self.prefix} convert_audio codec')
        bMaker.ibutton('Bitrate', f'{self.prefix} convert_audio bitrate')
        bMaker.ibutton('Sample Rate', f'{self.prefix} convert_audio sample_rate')
        bMaker.ibutton('Channels', f'{self.prefix} convert_audio channels')
        bMaker.ibutton('Extension', f'{self.prefix} convert_audio extension')
        bMaker.ibutton('🔧 Custom FFmpeg', f'{self.prefix} convert_audio custom', 'footer')
        
        # Navigation
        if len(ddict['selected_types']) > 1:
            current_idx = ddict['selected_types'].index('audio')
            if current_idx < len(ddict['selected_types']) - 1:
                bMaker.ibutton('➡️ Next Type', f'{self.prefix} convert_config next', 'footer')
            else:
                bMaker.ibutton('➡️ Review', f'{self.prefix} convert_config review', 'footer')
        else:
            bMaker.ibutton('➡️ Review', f'{self.prefix} convert_config review', 'footer')
        
        bMaker.ibutton('↩️ Back', f'{self.prefix} convert_config back', 'footer')
        bMaker.ibutton('❌ Cancel', f'{self.prefix} cancel', 'footer')
        
        text += f'<i>Time Out: {get_readable_time(VT_TIMEOUT - (time()-self._time))}</i>'
        await self.update_message(text, bMaker.build(3))
    
    async def _subtitle_configuration(self, ddict, bMaker, text):
        """Subtitle conversion configuration"""
        ssettings = ddict.get('subtitle_settings', {})
        subtitle_streams = ddict['subtitle_streams']
        
        # Show current settings
        text += '<b>Current Subtitle Settings:</b>\n'
        text += f"Mode: <code>{ssettings.get('mode', 'Not Set')}</code>\n"
        text += f"Format: <code>{ssettings.get('format', 'Not Set')}</code>\n"
        text += f"Encoding: <code>{ssettings.get('encoding', 'Not Set')}</code>\n"
        if ssettings.get('mode') == 'hardsub':
            text += f"HardSub Stream: <code>{ssettings.get('hardsub_stream', 'Not Set')}</code>\n"
        text += '\n'
        
        # Mode selection
        bMaker.ibutton('📝 Convert Format', f'{self.prefix} convert_subtitle mode_convert', 'header')
        bMaker.ibutton('🔥 HardSub', f'{self.prefix} convert_subtitle mode_hardsub', 'header')
        
        # Format buttons (if convert mode)
        if ssettings.get('mode') == 'convert':
            bMaker.ibutton('SRT', f'{self.prefix} convert_subtitle format_srt')
            bMaker.ibutton('ASS', f'{self.prefix} convert_subtitle format_ass')
            bMaker.ibutton('VTT', f'{self.prefix} convert_subtitle format_vtt')
            bMaker.ibutton('SUB', f'{self.prefix} convert_subtitle format_sub')
            
            bMaker.ibutton('UTF-8', f'{self.prefix} convert_subtitle encoding_utf8', 'footer')
            bMaker.ibutton('ASCII', f'{self.prefix} convert_subtitle encoding_ascii', 'footer')
        
        # HardSub stream selection
        elif ssettings.get('mode') == 'hardsub':
            text += '<b>Select Subtitle Stream to Burn:</b>\n'
            for idx in subtitle_streams:
                stream_info = ddict['stream'][idx]
                btn_text = f"✓ {stream_info['info']}" if ssettings.get('hardsub_stream') == idx else stream_info['info']
                bMaker.ibutton(btn_text, f'{self.prefix} convert_subtitle hardsub_{idx}')
        
        # Navigation
        bMaker.ibutton('➡️ Review', f'{self.prefix} convert_config review', 'footer')
        bMaker.ibutton('↩️ Back', f'{self.prefix} convert_config back', 'footer')
        bMaker.ibutton('❌ Cancel', f'{self.prefix} cancel', 'footer')
        
        text += f'<i>Time Out: {get_readable_time(VT_TIMEOUT - (time()-self._time))}</i>'
        await self.update_message(text, bMaker.build(3))
    
    async def _convert_review(self, ddict, bMaker):
        """Stage 3: Review all settings before processing"""
        text = (
            f'<b>ADVANCED CONVERT ~ {self._listener.tag}</b>\n'
            f'<code>{self.executor.name}</code>\n\n'
            f'🔹 <b>Step 3:</b> Review Settings\n\n'
        )
        
        # Show all selected settings
        if 'video' in ddict['selected_types']:
            text += '<b>📹 Video Settings:</b>\n'
            vsettings = ddict.get('video_settings', {})
            for key, value in vsettings.items():
                if value and value != 'Not Set':
                    text += f"  • {key.replace('_', ' ').title()}: <code>{value}</code>\n"
            text += '\n'
        
        if 'audio' in ddict['selected_types']:
            text += '<b>🎵 Audio Settings:</b>\n'
            asettings = ddict.get('audio_settings', {})
            for key, value in asettings.items():
                if value and value != 'Not Set':
                    text += f"  • {key.replace('_', ' ').title()}: <code>{value}</code>\n"
            text += '\n'
        
        if 'subtitle' in ddict['selected_types']:
            text += '<b>📝 Subtitle Settings:</b>\n'
            ssettings = ddict.get('subtitle_settings', {})
            for key, value in ssettings.items():
                if value and value != 'Not Set':
                    text += f"  • {key.replace('_', ' ').title()}: <code>{value}</code>\n"
            text += '\n'
        
        text += '✓ Press <b>Continue</b> to start conversion\n'
        
        bMaker.ibutton('✓ Continue', f'{self.prefix} convert_review continue', 'footer')
        bMaker.ibutton('🔄 Reset All', f'{self.prefix} convert_review reset', 'footer')
        bMaker.ibutton('↩️ Back', f'{self.prefix} convert_review back', 'footer')
        bMaker.ibutton('❌ Cancel', f'{self.prefix} cancel', 'footer')
        
        text += f'\n<i>Time Out: {get_readable_time(VT_TIMEOUT - (time()-self._time))}</i>'
        await self.update_message(text, bMaker.build(2))
    
    async def _convert_waiting_input(self, ddict, bMaker):
        """Stage 4: Waiting for user input"""
        waiting_for = ddict.get('waiting_for', {})
        param_type = waiting_for.get('type')  # 'video', 'audio', 'subtitle'
        param_name = waiting_for.get('param')  # 'crf', 'bitrate', etc.
        
        text = (
            f'<b>ADVANCED CONVERT ~ {self._listener.tag}</b>\n'
            f'<code>{self.executor.name}</code>\n\n'
            f'⏳ <b>Waiting for Input</b>\n\n'
        )
        
        # Show input instructions based on parameter
        instructions = {
            'crf': 'Send CRF value (0-51)\n• Lower = Better quality\n• 18-28 recommended\nExample: <code>23</code>',
            'bitrate': 'Send bitrate value\nExamples:\n• <code>2M</code> (2 Mbps)\n• <code>5000k</code> (5 Mbps)\n• <code>128k</code> (128 Kbps for audio)',
            'fps': 'Send FPS value\nExamples: <code>24</code>, <code>30</code>, <code>60</code>',
            'sample_rate': 'Send sample rate\nExamples: <code>44100</code>, <code>48000</code>',
            'custom': '🔧 Send custom FFmpeg command\n\nExample:\n<code>-c:v libx265 -crf 28 -preset medium</code>\n\nNote: Input/output files will be added automatically',
        }
        
        text += f'<b>Parameter:</b> {param_name.replace("_", " ").title()}\n\n'
        text += instructions.get(param_name, f'Send value for {param_name}')
        
        bMaker.ibutton('↩️ Cancel Input', f'{self.prefix} convert_input cancel', 'footer')
        bMaker.ibutton('❌ Cancel All', f'{self.prefix} cancel', 'footer')
        
        text += f'\n\n<i>Time Out: {get_readable_time(VT_TIMEOUT - (time()-self._time))}</i>'
        await self.update_message(text, bMaker.build(1))


    async def aisub_select(self, streams: dict = None):
        """AI Subtitle generation selector"""
        bMaker = ButtonMaker()
        
        if not self.executor.data:
            self.executor.data = {
                'stream': {},
                'audio_streams': [],
                'selected_audio': None,
                'selected_language': None,
                'stage': 'select_audio'  # stages: select_audio, select_language, confirm
            }
            
            # Collect all audio streams from video
            if streams:
                for stream in streams:
                    indexmap = stream.get('index')
                    codec_name = stream.get('codec_name')
                    codec_type = stream.get('codec_type')
                    lang = stream.get('tags', {}).get('language', 'unknown')
                    
                    if codec_type == 'audio':
                        self.executor.data['stream'][indexmap] = {
                            'info': f'Audio ~ {lang.upper()} ({codec_name})',
                            'name': codec_name,
                            'map': indexmap,
                            'type': codec_type,
                            'lang': lang
                        }
                        self.executor.data['audio_streams'].append(indexmap)
        
        ddict = self.executor.data
        audio_count = len(ddict['audio_streams'])
        stage = ddict.get('stage', 'select_audio')
        
        # Check if we have audio streams
        if audio_count == 0:
            text = (
                f'<b>AI SUBTITLE ERROR ~ {self._listener.tag}</b>\n'
                f'<code>{self.executor.name}</code>\n\n'
                f'⚠️ No audio streams found in video!'
            )
            bMaker.ibutton('❌ Cancel', f'{self.prefix} cancel')
            await self.update_message(text, bMaker.build())
            return
        
        # Stage 1: Select audio stream
        if stage == 'select_audio':
            text = (
                f'<b>AI SUBTITLE GENERATOR ~ {self._listener.tag}</b>\n'
                f'<code>{self.executor.name}</code>\n'
                f'<b>┌ </b>File Size: <b>{get_readable_file_size(self.executor.size)}</b>\n'
                f'<b>└ </b>Audio Streams: <b>{audio_count}</b>\n\n'
                f'🔹 <b>Step 1:</b> Select audio stream to transcribe\n\n'
                f'<b>Available Audio Streams:</b>\n'
            )
            
            for idx in ddict['audio_streams']:
                stream_info = ddict['stream'][idx]['info']
                bMaker.ibutton(stream_info, f'{self.prefix} aisub audio {idx}')
            
            bMaker.ibutton('❌ Cancel', f'{self.prefix} cancel', 'footer')
        
        # Stage 2: Select subtitle language
        elif stage == 'select_language':
            selected_audio = ddict.get('selected_audio')
            audio_info = ddict['stream'][selected_audio]['info']
            
            text = (
                f'<b>AI SUBTITLE GENERATOR ~ {self._listener.tag}</b>\n'
                f'<code>{self.executor.name}</code>\n\n'
                f'<b>Selected Audio:</b> {audio_info}\n\n'
                f'🔹 <b>Step 2:</b> Select subtitle language\n\n'
                f'<b>Available Languages:</b>\n'
            )
            
            # Popular languages for subtitles
            languages = {
                'en': '🇬🇧 English',
                'es': '🇪🇸 Spanish',
                'fr': '🇫🇷 French',
                'de': '🇩🇪 German',
                'it': '🇮🇹 Italian',
                'pt': '🇵🇹 Portuguese',
                'ru': '🇷🇺 Russian',
                'ja': '🇯🇵 Japanese',
                'ko': '🇰🇷 Korean',
                'zh': '🇨🇳 Chinese',
                'ar': '🇸🇦 Arabic',
                'hi': '🇮🇳 Hindi',
                'tr': '🇹🇷 Turkish',
                'nl': '🇳🇱 Dutch',
                'pl': '🇵🇱 Polish',
                'auto': '🔄 Auto Detect'
            }
            
            for code, name in languages.items():
                bMaker.ibutton(name, f'{self.prefix} aisub lang {code}')
            
            bMaker.ibutton('↩️ Back', f'{self.prefix} aisub back', 'footer')
            bMaker.ibutton('❌ Cancel', f'{self.prefix} cancel', 'footer')
        
        # Stage 3: Confirm
        elif stage == 'confirm':
            selected_audio = ddict.get('selected_audio')
            audio_info = ddict['stream'][selected_audio]['info']
            selected_lang = ddict.get('selected_language', 'auto')
            
            lang_names = {
                'en': 'English', 'es': 'Spanish', 'fr': 'French', 'de': 'German',
                'it': 'Italian', 'pt': 'Portuguese', 'ru': 'Russian', 'ja': 'Japanese',
                'ko': 'Korean', 'zh': 'Chinese', 'ar': 'Arabic', 'hi': 'Hindi',
                'tr': 'Turkish', 'nl': 'Dutch', 'pl': 'Polish', 'auto': 'Auto Detect'
            }
            
            text = (
                f'<b>AI SUBTITLE GENERATOR ~ {self._listener.tag}</b>\n'
                f'<code>{self.executor.name}</code>\n\n'
                f'<b>Selected Audio:</b> {audio_info}\n'
                f'<b>Subtitle Language:</b> {lang_names.get(selected_lang, selected_lang)}\n\n'
                f'⚙️ <b>Processing Info:</b>\n'
                f'• AI Model: Whisper (OpenAI)\n'
                f'• This may take several minutes\n'
                f'• Subtitle will be embedded in video\n\n'
                f'✓ Press Continue to start AI transcription'
            )
            
            bMaker.ibutton('✓ Continue', f'{self.prefix} aisub continue', 'footer')
            bMaker.ibutton('🔄 Reset', f'{self.prefix} aisub reset', 'footer')
            bMaker.ibutton('❌ Cancel', f'{self.prefix} cancel', 'footer')
        
        text += f'\n<i>Time Out: {get_readable_time(VT_TIMEOUT - (time()-self._time))}</i>'
        await self.update_message(text, bMaker.build(2))


    def streams_select(self, streams: dict=None):
        bMaker = ButtonMaker()
        if not self.executor.data:
            self.executor.data.setdefault('stream', {})
            self.executor.data['sdata'] = []
            for stream in streams:
                indexmap, codec_name, codec_type, lang = stream.get('index'), stream.get('codec_name'), stream.get('codec_type'), stream.get('tags', {}).get('language')
                if not lang:
                    lang = str(indexmap)
                if codec_type not in ['video', 'audio', 'subtitle']:
                    continue
                if codec_type == 'audio':
                    self.executor.data['is_audio'] = True
                elif codec_type == 'subtitle':
                    self.executor.data['is_sub'] = True
                self.executor.data['stream'][indexmap] = {'info': f'{codec_type.title()} ~ {lang.upper()}',
                                                          'name': codec_name,
                                                          'map': indexmap,
                                                          'type': codec_type,
                                                          'lang': lang}
        mode, ddict = self.executor.mode, self.executor.data
        for key, value in ddict['stream'].items():
            if mode == 'extract':
                bMaker.ibutton(value['info'], f'{self.prefix} {mode} {key}')
                audext, subext, vidext = self.extension
                text = (f'<b>STREAM EXTRACT SETTINGS ~ {self._listener.tag}</b>\n'
                        f'<code>{self.executor.name}</code>\n'
                        f"<b>┌ </b>File Size: <b>{get_readable_file_size(self.executor.size)}</b>\n"
                        f'<b>├ </b>Video Format: <b>{vidext.upper()}</b>\n'
                        f'<b>├ </b>Audio Format: <b>{audext.upper()}</b>\n'
                        f'<b>├ </b>Subtitle Format: <b>{subext.upper()}</b>\n'
                        f"<b>└ </b>Alternative Mode: <b>{'✓ Enable' if ddict.get('alt_mode') else 'Disable'}</b>\n\n"
                        'Select avalilable stream below to unpack!')
            else:
                if value['type'] != 'video':
                    bMaker.ibutton(value['info'], f'{self.prefix} {mode} {key}')
                text = (f'<b>STREAM REMOVE SETTINGS ~ {self._listener.tag}</b>\n'
                        f'<code>{self.executor.name}</code>\n'
                        f'File Size: <b>{get_readable_file_size(self.executor.size)}</b>\n')
                if sdata := ddict.get('sdata'):
                    text += '\nStream will removed:\n'
                    for i, sindex in enumerate(sdata, start=1):
                        text += f"{i}. {ddict['stream'][sindex]['info']}\n".replace('✓ ', '')
                text += '\nSelect avalilable stream below!'
        if mode == 'extract':
            bMaker.ibutton('✓ ALT Mode' if ddict.get('alt_mode') else 'ALT Mode', f"{self.prefix} {mode} alt {ddict.get('alt_mode', False)}", 'footer')
        if ddict.get('is_sub'):
            bMaker.ibutton('All Subs', f'{self.prefix} {mode} subtitle')
        if ddict.get('is_audio'):
            bMaker.ibutton('All Audio', f'{self.prefix} {mode} audio')
        bMaker.ibutton('Cancel', f'{self.prefix} cancel', 'footer')
        if mode == 'extract':
            for ext in self.extension:
                bMaker.ibutton(ext.upper(), f'{self.prefix} {mode} extension {ext}', 'header')
            bMaker.ibutton('Extract All', f'{self.prefix} {mode} video audio subtitle')
        else:
            bMaker.ibutton('Reset', f'{self.prefix} {mode} reset', 'header')
            bMaker.ibutton('Reverse', f'{self.prefix} {mode} reverse', 'header')
            bMaker.ibutton('Continue', f'{self.prefix} {mode} continue', 'footer')
        text += f'\n\n<i>Time Out: {get_readable_time(VT_TIMEOUT - (time()-self._time))}</i>'
        return text, bMaker.build(2)

    async def swap_select(self, streams: dict = None):
        bMaker = ButtonMaker()
    
        # ---------- build stream list when provided ----------
        if streams:
            self.executor.data = {
                'stream': {},
                'audio_streams': [],
                'selected_order': []
            }
    
            for s in streams:
                if s.get('codec_type') != 'audio':
                    continue
    
                idx = s.get('index')
                codec = s.get('codec_name', 'unknown')
                lang = s.get('tags', {}).get('language', str(idx))
    
                self.executor.data['stream'][idx] = {
                    'info': f'Audio ~ {lang.upper()} ({codec})',
                    'lang': lang,
                    'codec': codec,
                }
    
                self.executor.data['audio_streams'].append(idx)
    
        # ---------- ensure structure exists ----------
        elif not self.executor.data:
            await self.update_message(
                "⚠️ No stream data available.",
                ButtonMaker().ibutton("Cancel", f"{self.prefix} cancel").build()
            )
            return
    
        ddict = self.executor.data
        audio_streams = ddict.get('audio_streams', [])
        selected = ddict.get('selected_order', [])
        audio_count = len(audio_streams)
    
        # ---------- edge case ----------
        if audio_count < 2:
            text = (
                f'<b>STREAM SWAP ERROR ~ {self._listener.tag}</b>\n'
                f'<code>{self.executor.name}</code>\n\n'
                f'⚠️ Need at least 2 audio streams\n'
                f'Found: <b>{audio_count}</b>'
            )
            bMaker.ibutton('❌ Cancel', f'{self.prefix} cancel')
            await self.update_message(text, bMaker.build())
            return
    
        # ---------- UI ----------
        text = (
            f'<b>STREAM SWAP SETTINGS ~ {self._listener.tag}</b>\n'
            f'<code>{self.executor.name}</code>\n'
            f'<b>┌ </b>File Size: <b>{get_readable_file_size(self.executor.size)}</b>\n'
            f'<b>└ </b>Audio Streams: <b>{audio_count}</b>\n\n'
        )
    
        if selected:
            text += '<b>Selected Order:</b>\n'
            for pos, idx in enumerate(selected, 1):
                info = ddict['stream'][idx]['info']
                text += f'{pos}. {info}\n'
            text += '\n'
        else:
            text += '🔹 Select streams in desired order\n\n'
    
        text += '<b>Available Streams:</b>\n'
    
        # ---------- buttons ----------
        for idx in audio_streams:
            info = ddict['stream'][idx]['info']
    
            if idx in selected:
                pos = selected.index(idx) + 1
                label = f'{pos}. ✓ {info}'
            else:
                label = info
    
            bMaker.ibutton(label, f'{self.prefix} swap {idx}')
    
        # ---------- footer ----------
        if len(selected) >= 2:
            bMaker.ibutton('✓ Done', f'{self.prefix} swap done', 'footer')
    
        if selected:
            bMaker.ibutton('🔄 Reset', f'{self.prefix} swap reset', 'footer')
    
        bMaker.ibutton('❌ Cancel', f'{self.prefix} cancel', 'footer')
    
        text += f'\n<i>Timeout: {get_readable_time(VT_TIMEOUT - (time()-self._time))}</i>'
    
        await self.update_message(text, bMaker.build(2))
        
    async def compress_select(self, streams: dict):
        self.executor.data = {}
        bMaker = ButtonMaker()
        for stream in streams:
            indexmap, codec_type, lang = stream.get('index'), stream.get('codec_type'), stream.get('tags', {}).get('language')
            if not lang:
                lang = str(indexmap)
            if codec_type == 'video' and indexmap == 0:
                self.executor.data['video'] = indexmap
            if codec_type == 'video' and 'video' not in self.executor.data:
                self.executor.data['video'] = indexmap
            if codec_type == 'audio':
                bMaker.ibutton(f'Audio ~ {lang.upper()}', f'{self.prefix} compress {indexmap}')
        bMaker.ibutton('Continue', f'{self.prefix} compress 0')
        bMaker.ibutton('Cancel', f'{self.prefix} cancel')
        await self.update_message(f'{self._listener.tag}, Select available audio or press <b>Continue (no audio)</b>.\n<code>{self.executor.name}</code>', bMaker.build(2))

    async def rmstream_select(self, streams: dict):
        self.executor.data = {}
        await self.update_message(*self.streams_select(streams))

    async def convert_select(self, streams: dict):
        bMaker = ButtonMaker()
        hvid = '1080p'
        resulution = {'1080p': 'Convert 1080p',
                      '720p': 'Convert 720p',
                      '540p': 'Convert 540p',
                      '480p': 'Convert 480p',
                      '360p': 'Convert 360p'}
        for stream in streams:
            if stream['codec_type'] == 'video':
                vid_height = f'{stream["height"]}p'
                if vid_height in resulution:
                    hvid = vid_height
                break
        keys = list(resulution)
        for key in keys[keys.index(hvid)+1:]:
            bMaker.ibutton(resulution[key], f'{self.prefix} convert {key}')
        bMaker.ibutton('Cancel', f'{self.prefix} cancel', 'footer')
        await self.update_message(f'{self._listener.tag}, Select available resulution to convert.\n<code>{self.executor.name}</code>', bMaker.build(2))

    async def subsync_select(self):
        bMaker = ButtonMaker()
        text = ''
        index = 1
        if not self.status:
            for possition, file in self.executor.data['list'].items():
                if file.endswith(('srt', '.ass')):
                    ref_file = self.executor.data['final'].get(possition, {}).get('ref', '')
                    text += f'{index}. {file} {"✓ " if ref_file else ""}\n'
                    but_txt = f'✓ {index}' if ref_file else index
                    bMaker.ibutton(but_txt, f'{self.prefix} subsync {possition}')
                    index += 1
            bMaker.ibutton('Cancel', f'{self.prefix} cancel', 'footer')
            if self.executor.data['final']:
                bMaker.ibutton('Continue', f'{self.prefix} subsync continue', 'footer')
        else:
            file: dict = self.executor.data['list'][self.status]
            text = (f'Current: <b>{file}</b>\n'
                    f'References: <b>{ref}</b>\n' if (ref := self.executor.data['final'].get(self.status, {}).get('ref')) else ''
                    '\nSelect Available References Below!\n')
            self.executor.data['final'][self.status] = {'file': file}
            for possition, file in self.executor.data['list'].items():
                if possition != self.status and file not in self.executor.data['final'].values():
                    text += f'{index}. {file}\n'
                    bMaker.ibutton(index, f'{self.prefix} subsync select {possition}')
                    index += 1
        await self.update_message(text, bMaker.build(5))

    async def extract_select(self, streams: dict):
        self.executor.data = {}
        ext = [None, None, 'mkv']
        for stream in streams:
            codec_name, codec_type = stream.get('codec_name'), stream.get('codec_type')
            if codec_type == 'audio' and not ext[0]:
                match codec_type:
                    case 'mp3':
                        ext[0] = 'ac3'
                    case 'aac' | 'ac3' | 'ac3' | 'eac3' | 'm4a' | 'mka' | 'wav' as value:
                        ext[0] = value
                    case _:
                        ext[0] = 'aac'
            elif codec_type == 'subtitle' and not ext[1]:
                ext[1] = 'srt' if codec_name == 'subrip' else 'ass'
        if not ext[0]:
            ext[0] = 'aac'
        if not ext[1]:
            ext[1] = 'srt'
        self.extension = ext
        await self.update_message(*self.streams_select(streams))

    async def get_buttons(self, *args):
        future = self._event_handler()
        if extra_mode := getattr(self, f'{self.executor.mode}_select', None):
            await extra_mode(*args)
        await wrap_future(future)
        self.executor.event.set()
        await delete_message(self._reply)
        if self.is_cancelled:
            self._listener._subprocess = 'cancelled'
            await self._listener.on_upload_error(f'{VID_MODE[self.executor.mode]} stopped by user!')

    async def _show_video_codec_menu(self):
        """Show video codec selection submenu"""
        bMaker = ButtonMaker()
        codecs = {
            'libx264': 'H.264 (Fast, Compatible)',
            'libx265': 'H.265 (Better Compression)',
            'libvpx-vp9': 'VP9 (Web Optimized)',
            'libaom-av1': 'AV1 (Future)',
            'mpeg4': 'MPEG4 (Legacy)'
        }
        
        text = '<b>Select Video Codec:</b>\n\n'
        for codec, desc in codecs.items():
            text += f'• <b>{codec}</b>: {desc}\n'
            bMaker.ibutton(desc, f'{self.prefix} convert_video_codec {codec}')
        
        bMaker.ibutton('↩️ Back', f'{self.prefix} convert_video back_menu', 'footer')
        await self.update_message(text, bMaker.build(1))
    
    async def _show_video_preset_menu(self):
        """Show video preset selection submenu"""
        bMaker = ButtonMaker()
        presets = ['ultrafast', 'superfast', 'veryfast', 'faster', 'fast', 'medium', 'slow', 'slower', 'veryslow']
        
        text = '<b>Select Encoding Preset:</b>\n• Faster = Bigger file\n• Slower = Smaller file\n\n'
        for preset in presets:
            bMaker.ibutton(preset.title(), f'{self.prefix} convert_video_preset {preset}')
        
        bMaker.ibutton('↩️ Back', f'{self.prefix} convert_video back_menu', 'footer')
        await self.update_message(text, bMaker.build(3))
    
    async def _show_video_resolution_menu(self):
        """Show video resolution selection submenu"""
        bMaker = ButtonMaker()
        resolutions = ['2160p', '1440p', '1080p', '720p', '540p', '480p', '360p']
        
        text = '<b>Select Resolution:</b>\n\n'
        for res in resolutions:
            bMaker.ibutton(res, f'{self.prefix} convert_video_resolution {res}')
        
        bMaker.ibutton('🔧 Custom', f'{self.prefix} convert_video resolution_custom', 'footer')
        bMaker.ibutton('↩️ Back', f'{self.prefix} convert_video back_menu', 'footer')
        await self.update_message(text, bMaker.build(3))
    
    async def _show_video_extension_menu(self):
        """Show video extension selection submenu"""
        bMaker = ButtonMaker()
        extensions = ['.mkv', '.mp4', '.avi', '.webm', '.mov']
        
        text = '<b>Select Output Extension:</b>\n\n'
        for ext in extensions:
            bMaker.ibutton(ext, f'{self.prefix} convert_video_extension {ext}')
        
        bMaker.ibutton('↩️ Back', f'{self.prefix} convert_video back_menu', 'footer')
        await self.update_message(text, bMaker.build(3))
    
    async def _show_video_pixfmt_menu(self):
        """Show pixel format selection submenu"""
        bMaker = ButtonMaker()
        formats = {'yuv420p': '4:2:0 (Standard)', 'yuv444p': '4:4:4 (High Quality)', 'yuv420p10le': '10-bit'}
        
        text = '<b>Select Pixel Format:</b>\n\n'
        for fmt, desc in formats.items():
            bMaker.ibutton(desc, f'{self.prefix} convert_video_pixfmt {fmt}')
        
        bMaker.ibutton('↩️ Back', f'{self.prefix} convert_video back_menu', 'footer')
        await self.update_message(text, bMaker.build(1))
    
    async def _show_audio_codec_menu(self):
        """Show audio codec selection submenu"""
        bMaker = ButtonMaker()
        codecs = {'aac': 'AAC', 'libmp3lame': 'MP3', 'ac3': 'AC3', 'libopus': 'Opus', 'flac': 'FLAC', 'libvorbis': 'Vorbis'}
        
        text = '<b>Select Audio Codec:</b>\n\n'
        for codec, name in codecs.items():
            bMaker.ibutton(name, f'{self.prefix} convert_audio_codec {codec}')
        
        bMaker.ibutton('↩️ Back', f'{self.prefix} convert_audio back_menu', 'footer')
        await self.update_message(text, bMaker.build(3))
    
    async def _show_audio_channels_menu(self):
        """Show audio channels selection submenu"""
        bMaker = ButtonMaker()
        channels = {'1': 'Mono', '2': 'Stereo', '6': '5.1 Surround', '8': '7.1 Surround'}
        
        text = '<b>Select Audio Channels:</b>\n\n'
        for ch, name in channels.items():
            bMaker.ibutton(name, f'{self.prefix} convert_audio_channels {ch}')
        
        bMaker.ibutton('↩️ Back', f'{self.prefix} convert_audio back_menu', 'footer')
        await self.update_message(text, bMaker.build(2))
    
    async def _show_audio_extension_menu(self):
        """Show audio extension selection submenu"""
        bMaker = ButtonMaker()
        extensions = ['.mp3', '.m4a', '.aac', '.ac3', '.mka', '.flac', '.ogg', '.opus']
        
        text = '<b>Select Audio Extension:</b>\n\n'
        for ext in extensions:
            bMaker.ibutton(ext, f'{self.prefix} convert_audio_extension {ext}')
        
        bMaker.ibutton('↩️ Back', f'{self.prefix} convert_audio back_menu', 'footer')
        await self.update_message(text, bMaker.build(4))
    
    async def _show_audio_stream_selection(self):
        """Show audio stream selection for specific conversion"""
        bMaker = ButtonMaker()
        ddict = self.executor.data
        audio_streams = ddict['audio_streams']
        selected = ddict.get('audio_settings', {}).get('selected_streams', [])
        
        text = '<b>Select Audio Streams to Convert:</b>\n\n'
        for idx in audio_streams:
            stream_info = ddict['stream'][idx]['info']
            btn_text = f"✓ {stream_info}" if idx in selected else stream_info
            bMaker.ibutton(btn_text, f'{self.prefix} convert_audio_stream {idx}')
        
        bMaker.ibutton('✓ Done', f'{self.prefix} convert_audio_stream done', 'footer')
        bMaker.ibutton('↩️ Back', f'{self.prefix} convert_audio back_menu', 'footer')
        await self.update_message(text, bMaker.build(1))


async def cb_extra(_, query: CallbackQuery, obj: ExtraSelect):
    data = query.data.split()
    match data[1]:
        case 'merge_start':
            await query.answer()
        
            try:
                await delete_message(query.message)
            except:
                pass
        
            # ❌ DO NOT set event here
        
            await obj.merge_select(obj.executor.data['files'])
        
        case 'merge_skip':
            await query.answer('Merging all...')
        
            files = obj.executor.data.get('files') or []
        
            if not files:
                obj.event.set()
                return
        
            obj.executor.data['instructions'] = [{
                'files': files,
                'name': obj.executor.name or ospath.basename(files[0]),
                'copy_only': False,
            }]
        
            try:
                await delete_message(query.message)
            except:
                pass
        
            if not obj.event.is_set():
                obj.event.set()
                
        case 'hard_sub':
            ddict = obj.executor.data
            value = data[2]
            
            if value == 'continue':
                if ddict.get('selected_sub') is not None:
                    await query.answer('Starting HardSub...')
                    obj.event.set()
                else:
                    await query.answer('Please select a subtitle stream!', True)
            
            elif value.isdigit():
                stream_idx = int(value)
                ddict['selected_sub'] = stream_idx
                ddict['selected_lang'] = ddict['stream'][stream_idx]['lang']
                await query.answer('Subtitle selected!')
                await obj.hard_sub_select(None)
                
        case 'cancel':
            await query.answer()
            obj.is_cancelled = obj.executor.is_cancelled = True
            obj.executor.data = None
            obj.event.set()
        case 'subsync':
            if data[2].isdigit():
                obj.status = int(data[2])
            elif data[2] == 'select':
                obj.executor.data['final'][obj.status]['ref'] = obj.executor.data['list'][int(data[3])]
                obj.status = ''
            elif data[2] == 'continue':
                obj.event.set()
                return
            await gather(query.answer(), obj.subsync_select())
        case 'compress':
            await query.answer()
            obj.executor.data['audio'] = int(data[2])
            obj.event.set()
        case 'convert':
            await query.answer()
            obj.executor.data = data[2]
            obj.event.set()
        case 'rmstream':
            ddict: dict = obj.executor.data
            match data[2]:
                case 'reset':
                    if sdata := ddict['sdata']:
                        await query.answer()
                        for mapindex in sdata:
                            info = ddict['stream'][mapindex]['info']
                            ddict['stream'][mapindex]['info'] = info.replace('✓ ', '')
                        sdata.clear()
                        await obj.update_message(*obj.streams_select())
                    else:
                        await query.answer('No any selected stream to reset!', True)
                case 'continue':
                    if ddict['sdata']:
                        await query.answer()
                        obj.event.set()
                    else:
                        await query.answer('Please select at least one stream!', True)
                case 'audio' | 'subtitle' as value:
                    await query.answer()
                    obj.executor.data['key'] = value
                    obj.event.set()
                case 'reverse':
                    if ddict['sdata']:
                        await query.answer()
                        new_sdata = [x for x in ddict['stream'] if x not in ddict['sdata'] and x != 0]
                        for key, value in ddict['stream'].items():
                            info = value['info']
                            ddict['stream'][key]['info'] = f'✓ {info}' if key in new_sdata else info.replace('✓ ', '')
                        ddict['sdata'] = new_sdata
                        await obj.update_message(*obj.streams_select())
                    else:
                        await query.answer('No any selected stream to revers!', True)
                case value:
                    await query.answer()
                    mapindex = int(value)
                    info = ddict['stream'][mapindex]['info']
                    if mapindex in ddict['sdata']:
                        ddict['sdata'].remove(mapindex)
                        ddict['stream'][mapindex]['info'] = info.replace('✓ ', '')
                    else:
                        ddict['sdata'].append(mapindex)
                        ddict['stream'][mapindex]['info'] = f'✓ {info}'
                    await obj.update_message(*obj.streams_select())
        
        case 'hardsub':
            idx = int(data[2])
            obj.executor.data = {
                'selected_sub': obj.executor.data['stream'][idx]
            }
            await query.answer('Subtitle selected')
            obj.event.set()
        
        case 'swap':
            ddict = obj.executor.data or {}
        
            value = data[2]
        
            if 'audio_streams' not in ddict:
                await query.answer('No audio streams found', True)
                return
        
            if value == 'done':
                selected = ddict.get('selected_order', [])
                if len(selected) < 2:
                    await query.answer('Select at least 2 streams', True)
                    return
        
                await query.answer('Starting swap...')
                obj.event.set()
                return
        
            if value == 'reset':
                ddict['selected_order'] = []
                await query.answer('Selection cleared')
                await obj.swap_select(None)
                return
        
            if value.isdigit():
                idx = int(value)
        
                if idx not in ddict['audio_streams']:
                    await query.answer('Invalid stream', True)
                    return
        
                order = ddict.setdefault('selected_order', [])
        
                if idx in order:
                    order.remove(idx)
                    await query.answer('Removed')
                else:
                    order.append(idx)
                    await query.answer(f'Added as #{len(order)}')
        
                await obj.swap_select(None)
                return
                
        
        case 'extract':
            value = data[2]
            await query.answer()
            if value in ('extension', 'alt'):
                ext_dict = {'ass': [1, 'srt'],
                            'srt': [1, 'ass'],
                            'aac': [0, 'ac3'],
                            'ac3': [0, 'eac3'],
                            'eac3': [0, 'm4a'],
                            'm4a': [0, 'mka'],
                            'mka': [0, 'wav'],
                            'wav': [0, 'aac'],
                            'mp4': [2, 'mkv'],
                            'mkv': [2, 'mp4']}
                if data[3] in ext_dict:
                    index, ext = ext_dict[data[3]]
                    obj.extension[index] = ext
                if value == 'alt':
                    obj.executor.data['alt_mode'] = not literal_eval(data[3])
                await obj.update_message(*obj.streams_select())
            else:
                obj.executor.data.update({'key': int(value) if value.isdigit() else data[2:],
                                          'extension': obj.extension})
                obj.event.set()
        
        case 'convert_type':
            ddict = obj.executor.data
            value = data[2]
            
            if value == 'next':
                if ddict.get('selected_types'):
                    ddict['stage'] = 'configure'
                    ddict['current_config_type'] = ddict['selected_types'][0]
                    await query.answer('Moving to configuration...')
                    await obj.advconvert_select(None)
                else:
                    await query.answer('Please select at least one stream type!', True)
            
            elif value in ['video', 'audio', 'subtitle']:
                selected_types = ddict.get('selected_types', [])
                if value in selected_types:
                    selected_types.remove(value)
                    await query.answer(f'{value.title()} deselected')
                else:
                    selected_types.append(value)
                    await query.answer(f'{value.title()} selected')
                await obj.advconvert_select(None)
        
        case 'convert_video':
            ddict = obj.executor.data
            value = data[2]
            vsettings = ddict.setdefault('video_settings', {})
            
            # Preset configurations
            if value == 'preset_hq':
                vsettings.update({'crf': '18', 'codec': 'libx265', 'preset': 'slow', 'extension': '.mkv'})
                await query.answer('High Quality preset applied!')
            elif value == 'preset_fast':
                vsettings.update({'crf': '28', 'codec': 'libx264', 'preset': 'ultrafast', 'extension': '.mp4'})
                await query.answer('Fast Encode preset applied!')
            elif value == 'preset_small':
                vsettings.update({'crf': '32', 'codec': 'libx265', 'preset': 'medium', 'extension': '.mkv'})
                await query.answer('Small Size preset applied!')
            elif value == 'preset_mobile':
                vsettings.update({'crf': '26', 'codec': 'libx264', 'preset': 'medium', 'resolution': '720p', 'extension': '.mp4'})
                await query.answer('Mobile preset applied!')
            
            # Individual settings - show submenu
            elif value == 'codec':
                await obj._show_video_codec_menu()
                return
            elif value == 'preset':
                await obj._show_video_preset_menu()
                return
            elif value == 'resolution':
                await obj._show_video_resolution_menu()
                return
            elif value == 'extension':
                await obj._show_video_extension_menu()
                return
            elif value == 'pix_fmt':
                await obj._show_video_pixfmt_menu()
                return
            
            # User input required
            elif value in ['crf', 'bitrate', 'fps', 'custom']:
                ddict['stage'] = 'waiting_input'
                ddict['waiting_for'] = {'type': 'video', 'param': value}
                await query.answer(f'Please send {value.upper()} value in chat')
                await obj.advconvert_select(None)
                return
            
            await obj.advconvert_select(None)
        
        case 'convert_video_codec':
            codec = data[2]
            obj.executor.data['video_settings']['codec'] = codec
            await query.answer(f'Codec set to {codec}')
            obj.executor.data['stage'] = 'configure'
            await obj.advconvert_select(None)
        
        case 'convert_video_preset':
            preset = data[2]
            obj.executor.data['video_settings']['preset'] = preset
            await query.answer(f'Preset set to {preset}')
            obj.executor.data['stage'] = 'configure'
            await obj.advconvert_select(None)
        
        case 'convert_video_resolution':
            if data[2] == 'custom':
                obj.executor.data['stage'] = 'waiting_input'
                obj.executor.data['waiting_for'] = {'type': 'video', 'param': 'resolution_custom'}
                await query.answer('Send custom resolution (e.g., 1920x1080)')
                await obj.advconvert_select(None)
            else:
                resolution = data[2]
                obj.executor.data['video_settings']['resolution'] = resolution
                await query.answer(f'Resolution set to {resolution}')
                obj.executor.data['stage'] = 'configure'
                await obj.advconvert_select(None)
        
        case 'convert_video_extension':
            ext = data[2]
            obj.executor.data['video_settings']['extension'] = ext
            await query.answer(f'Extension set to {ext}')
            obj.executor.data['stage'] = 'configure'
            await obj.advconvert_select(None)
        
        case 'convert_video_pixfmt':
            pixfmt = data[2]
            obj.executor.data['video_settings']['pix_fmt'] = pixfmt
            await query.answer(f'Pixel format set to {pixfmt}')
            obj.executor.data['stage'] = 'configure'
            await obj.advconvert_select(None)
        
        case 'convert_audio_codec':
            codec = data[2]
            obj.executor.data['audio_settings']['codec'] = codec
            await query.answer(f'Audio codec set to {codec}')
            obj.executor.data['stage'] = 'configure'
            await obj.advconvert_select(None)
        
        case 'convert_audio_channels':
            channels = data[2]
            obj.executor.data['audio_settings']['channels'] = channels
            await query.answer(f'Channels set to {channels}')
            obj.executor.data['stage'] = 'configure'
            await obj.advconvert_select(None)
        
        case 'convert_audio_extension':
            ext = data[2]
            obj.executor.data['audio_settings']['extension'] = ext
            await query.answer(f'Extension set to {ext}')
            obj.executor.data['stage'] = 'configure'
            await obj.advconvert_select(None)
        
        case 'convert_audio_stream':
            if data[2] == 'done':
                await query.answer('Stream selection completed')
                obj.executor.data['stage'] = 'configure'
                await obj.advconvert_select(None)
            else:
                stream_idx = int(data[2])
                selected = obj.executor.data.setdefault('audio_settings', {}).setdefault('selected_streams', [])
                if stream_idx in selected:
                    selected.remove(stream_idx)
                    await query.answer('Stream deselected')
                else:
                    selected.append(stream_idx)
                    await query.answer('Stream selected')
                await obj._show_audio_stream_selection()
        
        case 'convert_video' | 'convert_audio':
            if data[2] == 'back_menu':
                obj.executor.data['stage'] = 'configure'
                await query.answer('Going back...')
                await obj.advconvert_select(None)

        case 'convert_audio':
            ddict = obj.executor.data
            value = data[2]
            asettings = ddict.setdefault('audio_settings', {})
            
            # Preset configurations
            if value == 'preset_aac192':
                asettings.update({'codec': 'aac', 'bitrate': '192k', 'extension': '.m4a', 'apply_to': 'all'})
                await query.answer('AAC 192k preset applied!')
                await obj.advconvert_select(None)
            elif value == 'preset_aac320':
                asettings.update({'codec': 'aac', 'bitrate': '320k', 'extension': '.m4a', 'apply_to': 'all'})
                await query.answer('AAC 320k preset applied!')
                await obj.advconvert_select(None)
            elif value == 'preset_mp3':
                asettings.update({'codec': 'libmp3lame', 'bitrate': '320k', 'extension': '.mp3', 'apply_to': 'all'})
                await query.answer('MP3 320k preset applied!')
                await obj.advconvert_select(None)
            elif value == 'preset_flac':
                asettings.update({'codec': 'flac', 'bitrate': None, 'extension': '.flac', 'apply_to': 'all'})
                await query.answer('FLAC preset applied!')
                await obj.advconvert_select(None)
            
            # Apply to selection
            elif value == 'apply_all':
                asettings['apply_to'] = 'all'
                await query.answer('Will apply to all audio streams')
                await obj.advconvert_select(None)
            elif value == 'select_streams':
                await obj._show_audio_stream_selection()
            
            # Individual settings - show submenu
            elif value == 'codec':
                await obj._show_audio_codec_menu()
            elif value == 'channels':
                await obj._show_audio_channels_menu()
            elif value == 'extension':
                await obj._show_audio_extension_menu()
            
            # User input required
            elif value in ['bitrate', 'sample_rate', 'custom']:
                ddict['stage'] = 'waiting_input'
                ddict['waiting_for'] = {'type': 'audio', 'param': value}
                await query.answer(f'Please send {value.upper()} value in chat')
                await obj.advconvert_select(None)
            
            # Back to menu handler
            elif value == 'back_menu':
                ddict['stage'] = 'configure'
                await query.answer('Going back...')
                await obj.advconvert_select(None)
        
        case 'convert_subtitle':
            ddict = obj.executor.data
            value = data[2]
            ssettings = ddict.setdefault('subtitle_settings', {})
            
            if value == 'mode_convert':
                ssettings['mode'] = 'convert'
                await query.answer('Subtitle convert mode selected')
            elif value == 'mode_hardsub':
                ssettings['mode'] = 'hardsub'
                await query.answer('HardSub mode selected - select subtitle stream')
            
            # Format selection
            elif value.startswith('format_'):
                fmt = value.split('_')[1]
                ssettings['format'] = fmt
                await query.answer(f'{fmt.upper()} format selected')
            
            # Encoding selection
            elif value.startswith('encoding_'):
                enc = value.split('_')[1]
                ssettings['encoding'] = enc
                await query.answer(f'{enc.upper()} encoding selected')
            
            # HardSub stream selection
            elif value.startswith('hardsub_'):
                stream_idx = int(value.split('_')[1])
                ssettings['hardsub_stream'] = stream_idx
                await query.answer('Subtitle stream selected for hardsubbing')
            
            await obj.advconvert_select(None)
        
        
        case 'convert_config':
            ddict = obj.executor.data
            value = data[2]
            
            if value == 'next':
                # Move to next stream type configuration
                selected_types = ddict['selected_types']
                current = ddict.get('current_config_type')
                current_idx = selected_types.index(current)
                
                if current_idx < len(selected_types) - 1:
                    ddict['current_config_type'] = selected_types[current_idx + 1]
                    await query.answer(f'Configuring {selected_types[current_idx + 1]}...')
                else:
                    ddict['stage'] = 'review'
                    await query.answer('Moving to review...')
                await obj.advconvert_select(None)
            
            elif value == 'review':
                ddict['stage'] = 'review'
                await query.answer('Moving to review...')
                await obj.advconvert_select(None)
            
            elif value == 'back':
                ddict['stage'] = 'select_type'
                await query.answer('Going back...')
                await obj.advconvert_select(None)
        
        
        case 'convert_review':
            ddict = obj.executor.data
            value = data[2]
            
            if value == 'continue':
                await query.answer('Starting conversion...')
                obj.event.set()
            elif value == 'reset':
                await query.answer('Resetting all settings...')
                ddict['video_settings'] = {}
                ddict['audio_settings'] = {}
                ddict['subtitle_settings'] = {}
                ddict['selected_types'] = []
                ddict['stage'] = 'select_type'
                await obj.advconvert_select(None)
            elif value == 'back':
                ddict['stage'] = 'configure'
                selected_types = ddict['selected_types']
                ddict['current_config_type'] = selected_types[-1] if selected_types else None
                await query.answer('Going back...')
                await obj.advconvert_select(None)
        case 'convert_review':
            ddict = obj.executor.data
            value = data[2]
            
            if value == 'continue':
                await query.answer('Starting conversion...')
                obj.event.set()
            elif value == 'reset':
                await query.answer('Resetting all settings...')
                ddict['video_settings'] = {}
                ddict['audio_settings'] = {}
                ddict['subtitle_settings'] = {}
                ddict['selected_types'] = []
                ddict['stage'] = 'select_type'
                await obj.advconvert_select(None)
            elif value == 'back':
                ddict['stage'] = 'configure'
                selected_types = ddict['selected_types']
                ddict['current_config_type'] = selected_types[-1] if selected_types else None
                await query.answer('Going back...')
                await obj.advconvert_select(None)
        
        case 'convert_input':
            if data[2] == 'cancel':
                await query.answer('Input cancelled')
                obj.executor.data['stage'] = 'configure'
                obj.executor.data['waiting_for'] = None
                await obj.advconvert_select(None)

        case 'aisub':
            ddict = obj.executor.data
            value = data[2]
            
            if value == 'continue':
                if ddict.get('selected_audio') is not None and ddict.get('selected_language'):
                    await query.answer('Starting AI subtitle generation...')
                    obj.event.set()
                else:
                    await query.answer('Please complete all steps!', True)
            
            elif value == 'reset':
                await query.answer('Selection reset!')
                ddict['selected_audio'] = None
                ddict['selected_language'] = None
                ddict['stage'] = 'select_audio'
                await obj.aisub_select(None)
            
            elif value == 'back':
                await query.answer('Going back...')
                ddict['stage'] = 'select_audio'
                ddict['selected_language'] = None
                await obj.aisub_select(None)
            
            elif value == 'audio':
                stream_idx = int(data[3])
                ddict['selected_audio'] = stream_idx
                ddict['stage'] = 'select_language'
                await query.answer('Audio selected! Now select subtitle language.')
                await obj.aisub_select(None)
            
            elif value == 'lang':
                lang_code = data[3]
                ddict['selected_language'] = lang_code
                ddict['stage'] = 'confirm'
                await query.answer('Language selected!')
                await obj.aisub_select(None)