from __future__ import annotations
import shlex
import asyncio
from aiofiles import open as aiopen
from aiofiles.os import path as aiopath, makedirs, listdir, remove
from aioshutil import move
from ast import literal_eval
from asyncio import create_subprocess_exec, sleep, gather, Event
from asyncio.subprocess import PIPE
from natsort import natsorted
from os import path as ospath, walk
from time import time
from json import loads as jloads

from bot import download_dict, download_dict_lock, queue_dict_lock, non_queued_dl, LOGGER, VID_MODE, cpu_no, bot_loop
from bot.helper.ext_utils.bot_utils import sync_to_async, cmd_exec, new_task, MirrorStatus
from bot.helper.ext_utils.fs_utils import get_path_size, clean_target
from bot.helper.ext_utils.links_utils import get_url_name
from bot.helper.ext_utils.media_utils import get_document_type, get_media_info, get_subtitle_streams, FFMpegNew
from bot.helper.ext_utils.task_manager import is_queued
from bot.helper.mirror_leech_utils.status_utils.ffmpeg_status import FfmpegStatus
from bot.helper.mirror_leech_utils.status_utils.queue_status import QueueStatus
from bot.helper.telegram_helper.message_utils import update_all_messages
from bot.helper.video_utils.extra_selector import ExtraSelect
from bot.core.config_manager import Config, BinConfig
from bot.helper.utils import encode_dict
from bot.helper.uset_helper import wm_dict


BASE_CMD = [
    BinConfig.FFMPEG_NAME,
    "-hide_banner",
    "-loglevel", "error",
    "-progress", "pipe:1",
    "-nostats",
    "-threads", f"{max(1, cpu_no // 2)}",
            
]

async def get_metavideo(video_file):
    stdout, stderr, rcode = await cmd_exec([
        'ffprobe', '-hide_banner', '-print_format', 'json',
        '-show_format', '-show_streams', video_file
    ])
    if rcode != 0:
        LOGGER.error(stderr)
        return {}, {}
    try:
        metadata = jloads(stdout)
    except Exception as e:
        LOGGER.error(f"Failed to parse ffprobe json: {e}")
        return {}, {}
    filtered = []
    for s in metadata.get('streams', {}):
        typ = s.get('codec_type')
        if typ == 'video':
            if not s.get('width') or not s.get('height'):
                continue
        filtered.append(s)
    return filtered, metadata.get('format', {})

    
class VidEcxecutor:
    def __init__(self, listener, path: str, gid: str, metadata=False):
        self.data = None
        self.event = Event()
        self.listener = listener
        self.path = path
        self.name = ''
        self.outfile = ''
        self.size = 0
        self._metadata = metadata
        self._up_path = path
        self._gid = gid
        self._start_time = time()
        self._files = []
        self._qual = {'1080p': '1920', '720p': '1280', '540p': '960', '480p': '854', '360p': '640'}
        self.is_cancelled = False
    
    @staticmethod
    def _escape_filter_path(path: str) -> str:
        path = path.replace('\\', '\\\\')
        path = path.replace(':', '\\:')
        path = path.replace("'", "\\'")
        return path
        
    async def _get_newDir(self):
        """Get or create the temp output directory on the listener"""
        if not hasattr(self.listener, 'newDir') or not self.listener.newDir:
            self.listener.newDir = f'{self.listener.dir}1000'
        await makedirs(self.listener.newDir, exist_ok=True)
        return self.listener.newDir

    async def _queue(self, update=False):
        if self._metadata:
            add_to_queue, event = await is_queued(self.listener.uid)
            if add_to_queue:
                async with download_dict_lock:
                    download_dict[self.listener.uid] = QueueStatus(self.listener.name, self.size, self._gid, self.listener, 'dl')
                await self.listener.on_download_start()
                if update:
                    await sendStatusMessage(self.listener.message)
                await event.wait()
                async with download_dict_lock:
                    if self.listener.uid not in download_dict:
                        self.is_cancelled = True
                        return
            async with queue_dict_lock:
                non_queued_dl.add(self.listener.uid)

    async def execute(self):
        self._is_dir = await aiopath.isdir(self.path)
        self.mode, self.name, kwargs = self.listener.vidMode
        if self._metadata:
            if not self.name:
                self.name = get_url_name(self.path)
            try:
                self.size = int(self._metadata[1]['size'])
            except Exception as e:
                LOGGER.error(e)
                await self.listener.on_download_error('Invalid data, check the link!')
                return
            
        if not self.name:
            self.name = ospath.basename(self.path)
        if not self.name.upper().endswith(('MP4', 'MKV')):
            self.name += '.mkv'
            
        if self.mode in Config.DISABLE_MULTI_VIDTOOLS:
            if path := await self._get_video():
                self.path = path
            else:
                return self._up_path
        try:
            match self.mode:
                case 'vid_vid':
                    return await self._merge_vids()
                case 'vid_aud':
                    return await self._merge_auds()
                case 'vid_sub':
                    return await self._merge_subs(**kwargs)
                case 'trim':
                    return await self._vid_trimmer(**kwargs)
                case 'watermark':
                    return await self._vid_marker(**kwargs)
                case 'compress':
                    return await self._vid_compress(**kwargs)
                case 'subsync':
                    return await self._subsync(**kwargs)
                case 'rmstream':
                    return await self._rm_stream()
                case 'extract':
                    return await self._vid_extract()
                case 'encode':
                    return await self._encode(**kwargs)
                case 'swap':
                    return await self._swap()
                case 'hard_sub':
                    return await self._hardsub()
                case _:
                    return await self._vid_convert()
            
            if self.name:
                self.listener.name = self.name
                
        except Exception as e:
            LOGGER.error(e, exc_info=True)
        return self._up_path

    @new_task
    async def _start_handler(self, *args):
        await sleep(0.5)
        await ExtraSelect(self).get_buttons(*args)

    async def _send_status(self, status='wait'):
        if not isinstance(self.listener.ffmpeg, FFMpegNew):
            self.listener.ffmpeg = FFMpegNew(self.listener)
        else:
            self.listener.ffmpeg.clear()
            
        async with download_dict_lock:
            download_dict[self.listener.uid] = FfmpegStatus(listener=self.listener, obj=self.listener.ffmpeg, gid=self._gid, status=status)
        if self._metadata and status == 'wait':
            await sendStatusMessage(self.listener.message)
    
    async def _get_files(self):
        file_list = []
        if self._metadata:
            file_list.append(self.path)
        elif await aiopath.isfile(self.path):
            if (await get_document_type(self.path))[0]:
                file_list.append(self.path)
        else:
            for dirpath, _, files in await sync_to_async(walk, self.path):
                for file in natsorted(files):
                    file = ospath.join(dirpath, file)
                    if (await get_document_type(file))[0]:
                        file_list.append(file)
        return file_list

    async def _get_video(self):
        if not self._is_dir and (await get_document_type(self.path))[0]:
            return self.path
        for dirpath, _, files in await sync_to_async(walk, self.path):
            for file in natsorted(files):
                file = ospath.join(dirpath, file)
                if (await get_document_type(file))[0]:
                    return file

    async def _final_path(self, outfile=''):
        if self._metadata:
            self._up_path = outfile or self.outfile
        else:
            scan_dir = self._up_path if self._is_dir else ospath.split(self._up_path)[0]
            for dirpath, _, files in await sync_to_async(walk, scan_dir):
                for file in files:
                    if file.endswith(tuple(self.listener.excluded_extensions)):
                        await clean_target(ospath.join(dirpath, file))

            all_files = []
            for dirpath, _, files in await sync_to_async(walk, scan_dir):
                all_files.extend((dirpath, file) for file in files)
            if len(all_files) == 1:
                self._up_path = ospath.join(*all_files[0])
        
        return self._up_path

    async def _name_base_dir(self, path, info: str=None, multi: bool=False):
        base_dir, file_name = ospath.split(path)
        if not self.name or multi:
            if info:
                if await aiopath.isfile(path):
                    file_name = file_name.rsplit('.', 1)[0]
                file_name += f'_{info}.mkv'
            self.name = file_name
        if not self.name.upper().endswith('MKV'):
            self.name += '.mkv'
        return base_dir if await aiopath.isfile(path) else path

    def _make_out_path(self, input_path: str) -> str:
        """
        Build a temp output path inside listener.newDir, keeping the exact
        same filename as the input.  The caller is responsible for ensuring
        newDir already exists (call _get_newDir() first).
        """
        file_name = ospath.basename(input_path)
        return ospath.join(self.listener.newDir, file_name)

    async def _replace_original(self, original: str, processed: str) -> bool:
        # dest = same directory as original, but with processed filename (which already has new name)
        dest = ospath.join(ospath.dirname(original), ospath.basename(processed))
        ...
        await clean_target(original)
        await move(processed, dest)
        self.outfile = dest
        return True
    
    async def run_ffmpeg(self, cmd: list, input_path: str, status: str) -> bool:
        await self._get_newDir()
        LOGGER.info(f'FFMEPG CMD: {cmd}')
            
        out_path = ospath.join(self.listener.newDir, self.name)
        self.outfile = out_path
    
        # append output to command
        full_cmd = list(cmd) + [out_path]
        LOGGER.info(f'FFMEPG CMD: {cmd}')
        
        # --- set up FFMpeg progress tracker ---
        if not isinstance(self.listener.ffmpeg, FFMpegNew):
            self.listener.ffmpeg = FFMpegNew(self.listener)
        else:
            self.listener.ffmpeg.clear()

        self.listener.ffmpeg._total_time = (await get_media_info(input_path))[0]
        await self._send_status(status)

        self.listener._subprocess = await create_subprocess_exec(
            *full_cmd, stdout=PIPE, stderr=PIPE
        )

        progress_task = bot_loop.create_task(self.listener.ffmpeg._ffmpeg_progress())
        await self.listener._subprocess.wait()
        await progress_task

        stderr_bytes = await self.listener._subprocess.stderr.read()
        returncode = self.listener._subprocess.returncode

        # --- success ---
        if returncode == 0:
            # clean up tracked input files
            if not self.listener.seed:
                await gather(*[clean_target(f) for f in self._files])
            self._files.clear()

            # replace original with processed output
            ok = await self._replace_original(input_path, out_path)
            if not ok:
                self.is_cancelled = True
                return False
            return True

        # --- cancelled by signal ---
        if returncode == -9:
            self.is_cancelled = True
            if await aiopath.exists(out_path):
                await clean_target(out_path)
            return False

        # --- ffmpeg error ---
        err_output = stderr_bytes.decode(errors='ignore') or 'Unknown FFmpeg error'
        LOGGER.error(f"FFmpeg failed ({returncode}) → {err_output}")

        if await aiopath.exists(out_path):
            await clean_target(out_path)

        self._files.clear()
        self.is_cancelled = True
        return False

    async def _run_cmd(self, cmd: list, input_path: str, out_path: str, status: str = 'prog') -> bool:
        """
        Lightweight runner for one-shot commands that need explicit output paths
        (e.g. stream-extract helpers).  Does NOT auto-append output – callers
        must pass out_path explicitly.

        On success  → deletes input_path, moves out_path to input_path location.
        On failure  → cleans up out_path.
        """
        await self._send_status(status)
        LOGGER.info(cmd)

        self.listener._subprocess = await create_subprocess_exec(
            *cmd, stdout=PIPE, stderr=PIPE
        )

        _, code = await gather(
            self.progress(status),
            self.listener._subprocess.wait()
        )

        stdout, stderr = await self.listener._subprocess.communicate()

        if code == 0:
            if not self.listener.seed:
                await gather(*[clean_target(f) for f in self._files])
            self._files.clear()

            ok = await self._replace_original(input_path, out_path)
            if not ok:
                self.is_cancelled = True
                return False
            return True

        if code == -9:
            self.is_cancelled = True
            if await aiopath.exists(out_path):
                await clean_target(out_path)
            return False

        err_output = (
            stderr.decode(errors='ignore')
            or stdout.decode(errors='ignore')
            or 'Unknown FFmpeg error'
        )
        LOGGER.error(f"FFmpeg failed ({code}) → {err_output}")

        if await aiopath.exists(out_path):
            await clean_target(out_path)

        self._files.clear()
        self.is_cancelled = True
        return False

    # ------------------------------------------------------------------ #
    #  progress helper (unchanged)
    # ------------------------------------------------------------------ #
    async def progress(self, status):
        while self.listener._subprocess and self.listener._subprocess.returncode is None:
            await sleep(1)

    # ================================================================== #
    #  HARDSUB
    # ================================================================== #
    async def _hardsub(self):
        """Burn subtitles into video – output replaces the original file."""
        file_list = await self._get_files()
        multi = len(file_list) > 1

        if not file_list:
            return self._up_path

        font_size   = wm_dict.get('WM_FONTSIZE', 24)
        font_color  = wm_dict.get('WM_FONTCOLOR', 'white')
        opacity     = wm_dict.get('WM_OPACITY', 1.0)
        font_file   = wm_dict.get('WM_FONTFILE', '')

        first_file   = True
        selected_lang = None

        await self._get_newDir()

        for file_idx, file in enumerate(file_list):
            self.path = file

            if self._metadata:
                base_dir = self.listener.dir
                await makedirs(base_dir, exist_ok=True)
                streams = self._metadata[0]
            else:
                base_dir, (streams, _), self.size = await gather(
                    self._name_base_dir(self.path, '', multi),
                    get_metavideo(self.path),
                    get_path_size(self.path)
                )

            subtitle_streams = [s for s in streams if s.get('codec_type') == 'subtitle']

            if not subtitle_streams:
                LOGGER.warning(f'No subtitles in {self.path}, skipping...')
                continue

            if first_file:
                self.data = {
                    'file_index': file_idx,
                    'total_files': len(file_list),
                    'current_file': self.path
                }
                await self._start_handler(streams)
                await gather(self._send_status(), self.event.wait())
                await self._queue()

                if self.is_cancelled or not self.data.get('selected_sub'):
                    return self._up_path

                selected_lang     = self.data.get('selected_lang')
                selected_sub_idx  = self.data.get('selected_sub')
                first_file        = False
            else:
                matching_sub = None
                for s in subtitle_streams:
                    lang = s.get('tags', {}).get('language', '')
                    if lang == selected_lang:
                        matching_sub = s.get('index')
                        break

                if matching_sub is None:
                    LOGGER.warning(f'No {selected_lang} subtitle in {self.path}')
                    self.data = {
                        'file_index': file_idx,
                        'total_files': len(file_list),
                        'current_file': self.path
                    }
                    await self._start_handler(streams)
                    await gather(self._send_status(), self.event.wait())

                    if self.is_cancelled or not self.data.get('selected_sub'):
                        return self._up_path

                    selected_sub_idx = self.data.get('selected_sub')
                else:
                    selected_sub_idx = matching_sub

            # Extract subtitle to temp dir
            temp_sub = ospath.join(self.listener.newDir, f'hardsub_{file_idx}.srt')
            extract_cmd = BASE_CMD.copy() + [
                '-i', self.path,
                '-map', f'0:{selected_sub_idx}',
                '-y', temp_sub
            ]

            proc = await create_subprocess_exec(*extract_cmd, stdout=PIPE, stderr=PIPE)
            await proc.wait()

            if not await aiopath.exists(temp_sub):
                LOGGER.error(f'Failed to extract subtitle from {self.path}')
                continue

            self._files.append(self.path)

            sub_path   = temp_sub.replace('\\', '/').replace(':', '\\:')
            force_style = f"FontSize={font_size},PrimaryColour=&H{self._color_to_hex(font_color)},Alignment=2"

            if font_file and await aiopath.exists(font_file):
                font_name = ospath.basename(font_file).rsplit('.', 1)[0]
                force_style += f",FontName={font_name}"

            if opacity < 1.0:
                alpha = int((1.0 - opacity) * 255)
                force_style += f",PrimaryColour=&H{alpha:02X}FFFFFF"

            subtitle_filter = f"subtitles='{sub_path}':force_style='{force_style}'"

            cmd = BASE_CMD.copy() + [
                '-i', self.path,
                '-vf', subtitle_filter,
                '-map', '0:v',
                '-map', '0:a?',
                '-c:v', 'libx264',
                '-preset', 'medium',
                '-crf', '23',
                '-c:a', 'copy',
                '-movflags', '+faststart',
                '-max_muxing_queue_size', '9999',
            ]

            # run_ffmpeg appends output path automatically
            ok = await self.run_ffmpeg(cmd, self.path, status=MirrorStatus.STATUS_HARDSUB)
            await clean_target(temp_sub)

            if not ok:
                return

        return await self._final_path()

    def _color_to_hex(self, color):
        color_map = {
            'white': 'FFFFFF', 'black': '000000', 'red': '0000FF',
            'green': '00FF00', 'blue': 'FF0000', 'yellow': '00FFFF',
            'cyan': 'FFFF00', 'magenta': 'FF00FF'
        }
        return color_map.get(color.lower(), 'FFFFFF')

    # ================================================================== #
    #  SWAP AUDIO STREAMS
    # ================================================================== #
    async def _swap(self):
        await self._queue(True)
        if self.is_cancelled:
            return
    
        file_list = await self._get_files()
        if not file_list:
            return self._up_path
    
        multi = len(file_list) > 1
    
        first_file = file_list[0]
        base_dir, (streams, _), self.size = await gather(
            self._name_base_dir(first_file, 'Swap', multi),
            get_metavideo(first_file),
            get_path_size(first_file)
        )
    
        self.event.clear()
        await self._start_handler(streams)
        await gather(self._send_status(), self.event.wait())
        await self._queue()
    
        if self.is_cancelled:
            return
    
        selected_order = self.data.get('selected_order', [])
        if not selected_order:
            return self._up_path
    
        selected_langs = [
            self.data['stream'][i]['lang']
            for i in selected_order
            if i in self.data['stream']
        ]
    
        await self._get_newDir()
    
        for file in file_list:
            self.path = file
    
            base_dir, (streams, _), self.size = await gather(
                self._name_base_dir(file, '', multi),
                get_metavideo(file),
                get_path_size(file)
            )
    
            audio_streams = [s for s in streams if s.get('codec_type') == 'audio']
            if not audio_streams:
                continue
    
            matched = []
            for lang in selected_langs:
                match = next(
                    (s['index'] for s in audio_streams
                     if s.get('tags', {}).get('language') == lang),
                    None
                )
                if match is not None and match not in matched:
                    matched.append(match)
    
            if not matched:
                matched = [s['index'] for s in audio_streams]
    
            maps = ['-map', '0:v:0?']
    
            for idx in matched:
                maps += ['-map', f'0:{idx}']
    
            for s in audio_streams:
                if s['index'] not in matched:
                    maps += ['-map', f'0:{s["index"]}']
    
            maps += ['-map', '0:s?']
    
            cmd = BASE_CMD[:] + ['-i', file] + maps + [
                '-map', '-0:t',
                '-c', 'copy',
                '-disposition:a', '0',
                '-disposition:a:0', 'default+forced',
                '-movflags', '+faststart',
                '-avoid_negative_ts', 'make_zero',
                '-fflags', '+genpts',
                '-max_muxing_queue_size', '1024'
            ]
    
            self._files.append(self.path)
    
            ok = await self.run_ffmpeg(cmd, self.path, status=MirrorStatus.STATUS_STREAM_SWAP)
            if not ok:
                return
    
        return await self._final_path()
        
    async def _encode(self, **kwargs):
        await self._queue(True)
        if self.is_cancelled:
            return
    
        file_list = await self._get_files()
        await self._get_newDir()
    
        for file in file_list:
            self.path = file
    
            if self._metadata:
                base_dir = self.listener.dir
                await makedirs(base_dir, exist_ok=True)
            else:
                base_dir, self.size = await gather(
                    self._name_base_dir(self.path, '', len(file_list) > 1),
                    get_path_size(self.path),
                )
    
            try:
                proc = await create_subprocess_exec(
                    'ffprobe', '-v', 'quiet', '-print_format', 'json',
                    '-show_streams', self.path,
                    stdout=PIPE, stderr=PIPE
                )
                stdout, _ = await proc.communicate()
                streams = jloads(stdout.decode()).get('streams', []) if stdout else []
            except Exception:
                LOGGER.exception("ffprobe failed")
                streams = []
    
            v_idx, a_idx, s_idx = [], [], []
            for s in streams:
                t = s.get('codec_type')
                if t == 'video':
                    if s.get('disposition', {}).get('attached_pic', 0) == 1:
                        continue
                    if (s.get('codec_name') or '').lower() in ('mjpeg', 'png', 'jpg'):
                        continue
                    v_idx.append(s['index'])
                elif t == 'audio':
                    a_idx.append(s['index'])
                elif t == 'subtitle':
                    s_idx.append(s['index'])
    
            maps = []
            for i in v_idx + a_idx + s_idx:
                maps += ['-map', f'0:{i}']
    
            encode_type = kwargs.get('encode_type', '')
            cmd = BASE_CMD[:] + ['-i', self.path]
    
            if encode_type == 'custom':
                user_ffmpeg_cmd = kwargs.get('user_ffmpeg_cmd', '')
                if user_ffmpeg_cmd:
                    cmd += shlex.split(user_ffmpeg_cmd)
    
            else:
                settings = encode_dict.get(encode_type, {}) if encode_type else {}
    
                if not settings:
                    settings = {
                        "video_codec": "libx264",
                        "crf": "24",
                        "preset": "medium",
                        "audio_codec": "copy"
                    }
    
                if v := settings.get("video_codec"):
                    cmd += ['-c:v', v]
    
                if v := settings.get("crf"):
                    cmd += ['-crf', str(v)]
    
                if v := settings.get("preset"):
                    cmd += ['-preset', str(v)]
    
                if v := settings.get("pixel_format"):
                    cmd += ['-pix_fmt', str(v)]
    
                if v := settings.get("resolution"):
                    cmd += ['-vf', f'scale={v}']
    
                if v := settings.get("audio_codec"):
                    cmd += ['-c:a', str(v)]
    
                    if v == "libopus":
                        cmd += ['-ac', '2']
    
                if v := settings.get("audio_bitrate"):
                    cmd += ['-b:a', str(v)]
    
            cmd += [
                '-c:s', 'copy',
                '-movflags', '+faststart',
                '-avoid_negative_ts', 'make_zero',
                '-fflags', '+genpts',
                '-max_muxing_queue_size', '1024',
                '-thread_queue_size', '512',
                '-rtbufsize', '16M'
            ]
    
            cmd += maps
    
            self._files.append(self.path)
    
            ok = await self.run_ffmpeg(cmd, self.path, status=MirrorStatus.STATUS_ENCODE)
            if not ok:
                return
    
        return await self._final_path()
    
    async def _vid_extract(self):
        if file_list := await self._get_files():
            if self._metadata:
                base_dir = ospath.join(self.listener.dir, self.name.split('.', 1)[0])
                await makedirs(base_dir, exist_ok=True)
                streams = self._metadata[0]
            else:
                main_video = file_list[0]
                base_dir, (streams, _), self.size = await gather(
                    self._name_base_dir(main_video, 'Extract', len(file_list) > 1),
                    get_metavideo(main_video),
                    get_path_size(main_video)
                )
            await self._start_handler(streams)
            await gather(self._send_status(), self.event.wait())
        else:
            return self._up_path

        await self._queue()
        if self.is_cancelled or not self.data:
            return self._up_path

        if await aiopath.isfile(self._up_path) or self._metadata:
            base_name = self.name if self._metadata else ospath.basename(self.path)
            self._up_path = ospath.join(base_dir, f'{base_name.rsplit(".", 1)[0]} (EXTRACT)')
            await makedirs(self._up_path, exist_ok=True)
            base_dir = self._up_path

        task_files = []
        keys = self.data.get('key')
        if not keys:
            return

        for file in file_list:
            self.path = file
            if not self._metadata:
                self.size = await get_path_size(self.path)
            base_name = self.name if self._metadata else ospath.basename(self.path)
            base_name = base_name.rsplit('.', 1)[0]

            async def _outfile_for(stream_data, out_ext):
                lang = (stream_data.get('lang') or 'UNKNOWN').upper()
                return ospath.join(base_dir, f"{base_name}_{lang}.{out_ext}")

            async def _run_extract(cmd, outfile):
                """Simple runner for extraction – does NOT replace original."""
                proc = await create_subprocess_exec(*cmd, stdout=PIPE, stderr=PIPE)
                await proc.wait()
                if await aiopath.exists(outfile) and await sync_to_async(ospath.getsize, outfile) > 0:
                    return True
                if await aiopath.exists(outfile):
                    await clean_target(outfile)
                return False

            async def _process_stream(stream_data):
                stype = stream_data['type']

                if stype == 'video':
                    outfile = await _outfile_for(stream_data, 'mkv')
                    cmd = BASE_CMD.copy() + [
                        '-i', self.path,
                        '-map', f"0:{stream_data['map']}",
                        '-c', 'copy', '-y', outfile
                    ]
                    return await _run_extract(cmd, outfile)

                if stype == 'subtitle':
                    outfile = await _outfile_for(stream_data, 'srt')
                    cmd = BASE_CMD.copy() + [
                        '-i', self.path,
                        '-map', f"0:{stream_data['map']}",
                        '-c', 'copy', '-y', outfile
                    ]
                    return await _run_extract(cmd, outfile)

                if stype == 'audio':
                    outfile_mp3 = await _outfile_for(stream_data, 'mp3')
                    cmd_mp3 = BASE_CMD.copy() + [
                        '-i', self.path,
                        '-map', f"0:{stream_data['map']}",
                        '-c', 'copy', '-y', outfile_mp3
                    ]
                    if await _run_extract(cmd_mp3, outfile_mp3):
                        return True
                    outfile_mka = await _outfile_for(stream_data, 'mka')
                    cmd_mka = BASE_CMD.copy() + [
                        '-i', self.path,
                        '-map', f"0:{stream_data['map']}",
                        '-c', 'copy', '-y', outfile_mka
                    ]
                    return await _run_extract(cmd_mka, outfile_mka)

                return False

            if isinstance(keys, int):
                stream_data = self.data['stream'][keys]
                success = await _process_stream(stream_data)
                if success:
                    task_files.append(file)
                else:
                    await move(file, self._up_path)
                if self.is_cancelled:
                    return
            else:
                extracted = False
                for stream_data in self.data['stream'].values():
                    if stream_data['type'] in keys:
                        if await _process_stream(stream_data):
                            extracted = True
                    if self.is_cancelled:
                        return
                if extracted:
                    task_files.append(file)
                else:
                    await move(file, self._up_path)

        await gather(*[clean_target(f) for f in task_files])
        return await self._final_path(self._up_path)

    # ================================================================== #
    #  VID CONVERT  (resolution downscale)
    # ================================================================== #
    async def _vid_convert(self):
        file_list = await self._get_files()
        multi = len(file_list) > 1
        if not file_list:
            return self._up_path

        if self._metadata:
            base_dir = self.listener.dir
            await makedirs(base_dir, exist_ok=True)
            streams = self._metadata[0]
        else:
            main_video = file_list[0]
            base_dir, (streams, _), self.size = await gather(
                self._name_base_dir(main_video, 'Convert', len(file_list) > 1),
                get_metavideo(main_video),
                get_path_size(main_video)
            )

        await self._start_handler(streams)
        await gather(self._send_status(), self.event.wait())
        await self._queue()

        if self.is_cancelled:
            return
        if not self.data:
            return self._up_path

        await self._get_newDir()

        for file in file_list:
            self.path = file
            if not self._metadata:
                _, self.size = await gather(
                    self._name_base_dir(self.path, '', multi),
                    get_path_size(self.path)
                )
            self._files.append(self.path)
            cmd = BASE_CMD.copy() + [
                '-i', self.path,
                '-map', '0:v:0',
                '-vf', f'scale={self._qual[self.data]}:-2',
                '-map', '0:a:?',
                '-map', '0:s:?',
                '-c:a', 'copy',
                '-c:s', 'copy',
            ]
            ok = await self.run_ffmpeg(cmd, self.path, status=MirrorStatus.STATUS_CONVERT)
            if not ok:
                return

        return await self._final_path()

    # ================================================================== #
    #  REMOVE STREAM
    # ================================================================== #
    async def _rm_stream(self):
        file_list = await self._get_files()
        multi = len(file_list) > 1
        if not file_list:
            return self._up_path

        if self._metadata:
            base_dir = self.listener.dir
            await makedirs(base_dir, exist_ok=True)
            streams = self._metadata[0]
        else:
            main_video = file_list[0]
            base_dir, (streams, _), self.size = await gather(
                self._name_base_dir(main_video, 'Remove', multi),
                get_metavideo(main_video),
                get_path_size(main_video)
            )

        await self._start_handler(streams)
        await gather(self._send_status(), self.event.wait())
        await self._queue()

        if self.is_cancelled:
            return
        if not self.data:
            return self._up_path

        await self._get_newDir()

        for file in file_list:
            self.path = file
            if not self._metadata:
                _, self.size = await gather(
                    self._name_base_dir(self.path, '', multi),
                    get_path_size(self.path)
                )
            key = self.data.get('key', '')
            self._files.append(self.path)

            cmd = BASE_CMD.copy() + ['-i', self.path]
            mapped = 0
            
            for s in streams:
                idx = s.get('index')
                stype = s.get('codec_type')
            
                if idx is None or stype not in ('video', 'audio', 'subtitle'):
                    continue
            
                if key == 'audio' and stype == 'audio':
                    continue
            
                if key == 'subtitle' and stype == 'subtitle':
                    continue
            
                if key not in ('audio', 'subtitle'):
                    if idx in self.data.get('sdata', []):
                        continue
            
                cmd.extend(('-map', f'0:{idx}?'))
                mapped += 1
            
            if mapped == 0:
                raise ValueError('No valid streams mapped')
            
            cmd.extend((
                '-map', '-0:t',
                '-c', 'copy'
            ))

            ok = await self.run_ffmpeg(cmd, self.path, status=MirrorStatus.STATUS_STREAM_REMOVE)
            if not ok:
                return

        return await self._final_path()

    # ================================================================== #
    #  TRIM
    # ================================================================== #
    async def _vid_trimmer(self, start_time, end_time):
        await self._queue(True)
        if self.is_cancelled:
            return

        file_list = await self._get_files()
        await self._get_newDir()

        for file in file_list:
            self.path = file
            if self._metadata:
                base_dir = self.listener.dir
                await makedirs(base_dir, exist_ok=True)
            else:
                base_dir, self.size = await gather(
                    self._name_base_dir(self.path, '', len(file_list) > 1),
                    get_path_size(self.path)
                )
            self._files.append(self.path)

            cmd = BASE_CMD.copy() + [
                '-i', self.path,
                '-ss', start_time,
                '-to', end_time,
                '-map', '0:v:0?',
                '-map', '0:a:?',
                '-map', '0:s:?',
                '-c:v', 'copy',
                '-c:a', 'copy',
                '-c:s', 'copy',
            ]
            ok = await self.run_ffmpeg(cmd, self.path, status=MirrorStatus.STATUS_TRIM)
            if not ok:
                return

        return await self._final_path()

    # ================================================================== #
    #  SUBSYNC
    # ================================================================== #
    async def _subsync(self, type: str = 'sync_manual'):
        if not self._is_dir:
            return self._up_path
        self.size = await get_path_size(self.path)
        list_files = natsorted(await listdir(self.path))
        if len(list_files) <= 1:
            return self._up_path

        sub_files, ref_files = [], []

        if type == 'sync_manual':
            index = 1
            self.data = {'list': {}, 'final': {}}
            for file in list_files:
                if (await get_document_type(ospath.join(self.path, file)))[0] or file.endswith(('.srt', '.ass')):
                    self.data['list'].update({index: file})
                    index += 1
            if not self.data['list']:
                return self._up_path
            await self._start_handler()
            await gather(self._send_status(), self.event.wait())

            if self.is_cancelled:
                return
            if not self.data or not self.data['final']:
                return self._up_path
            for key in self.data['final'].values():
                sub_files.append(ospath.join(self.path, key['file']))
                ref_files.append(ospath.join(self.path, key['ref']))
        else:
            for file in list_files:
                file_ = ospath.join(self.path, file)
                is_video, is_audio, _ = await get_document_type(file_)
                if is_video or is_audio:
                    ref_files.append(file_)
                elif file_.lower().endswith(('.srt', '.ass')):
                    sub_files.append(file_)

            if not sub_files:
                return self._up_path
            if not ref_files and len(sub_files) > 1:
                ref_files = list(filter(lambda x: (x, sub_files.remove(x)), sub_files))
            if not ref_files or not sub_files:
                return self._up_path

        await self._get_newDir()

        for sub_file, ref_file in zip(sub_files, ref_files):
            self._files.extend((sub_file, ref_file))
            self.size = await get_path_size(ref_file)
            self.name = ospath.basename(sub_file)
            name, ext = ospath.splitext(sub_file)

            # alass output in newDir, then replace original
            out_path = ospath.join(self.listener.newDir, ospath.basename(sub_file))
            cmd = ['alass', '--allow-negative-timestamps', ref_file, sub_file, out_path]

            await self._send_status(MirrorStatus.STATUS_SUB_SYNC)
            self.listener._subprocess = await create_subprocess_exec(*cmd, stdout=PIPE, stderr=PIPE)
            await self.listener._subprocess.wait()
            code = self.listener._subprocess.returncode

            if code == 0:
                ok = await self._replace_original(sub_file, out_path)
                if not ok:
                    self.is_cancelled = True
                    return
            elif code == -9:
                self.is_cancelled = True
                if await aiopath.exists(out_path):
                    await clean_target(out_path)
                return
            else:
                stderr = await self.listener._subprocess.stderr.read()
                LOGGER.error(f"alass failed ({code}) → {stderr.decode(errors='ignore')}")
                if await aiopath.exists(out_path):
                    await clean_target(out_path)
                self.is_cancelled = True
                return

        return await self._final_path(self._up_path)

    # ================================================================== #
    #  COMPRESS
    # ================================================================== #
    async def _vid_compress(self, quality=None):
        file_list = await self._get_files()
        multi = len(file_list) > 1
        if not file_list:
            return self._up_path

        if self._metadata:
            base_dir = self.listener.dir
            await makedirs(base_dir, exist_ok=True)
            streams = self._metadata[0]
        else:
            main_video = file_list[0]
            base_dir, (streams, _), self.size = await gather(
                self._name_base_dir(main_video, 'Compress', multi),
                get_metavideo(main_video),
                get_path_size(main_video)
            )

        await self._start_handler(streams)
        await gather(self._send_status(), self.event.wait())
        await self._queue()

        if self.is_cancelled:
            return
        if not isinstance(self.data, dict):
            return self._up_path

        await self._get_newDir()

        for file in file_list:
            self.path = file
            if not self._metadata:
                _, self.size = await gather(
                    self._name_base_dir(self.path, '', multi),
                    get_path_size(self.path)
                )
            self._files.append(self.path)

            cmd = BASE_CMD.copy() + [
                '-i', self.path,
                '-preset', Config.LIB265_PRESET,
                '-c:v', 'libx265',
                '-pix_fmt', 'yuv420p10le',
                '-crf', '24',
                '-profile:v', 'main10',
                '-map', f'0:{self.data["video"]}',
                '-map', '0:s:?', '-c:s', 'copy'
            ]

            if banner := Config.COMPRESS_BANNER:
                # write subtitle banner to newDir so it's not mixed with source
                sub_file = ospath.join(self.listener.newDir, 'subtitle.srt')
                self._files.append(sub_file)
                quality_filter = f',scale={self._qual[quality]}:-2' if quality else ''
                async with aiopen(sub_file, 'w') as f:
                    await f.write(f'1\n00:00:03,000 --> 00:00:08,00\n{banner}')
                cmd.extend((
                    '-vf', f"subtitles='{sub_file}'{quality_filter},unsharp,eq=contrast=1.07",
                    '-metadata', f'title={banner}',
                    '-metadata:s:v', f'title={banner}',
                    '-x265-params', 'no-info=1',
                    '-bsf:v', 'filter_units=remove_types=6'
                ))
            elif quality:
                cmd.extend(('-vf', f'scale={self._qual[quality]}:-2'))

            if self.data:
                cmd.extend(('-c:a', 'aac', '-b:a', '160k', '-map', f'0:{self.data["audio"]}?'))

            ok = await self.run_ffmpeg(cmd, self.path, status=MirrorStatus.STATUS_SUB_SYNC)
            if not ok:
                return

        return await self._final_path()

    # ================================================================== #
    #  WATERMARK
    # ================================================================== #
    async def _vid_marker(self, **kwargs):
        await self._queue(True)
        if self.is_cancelled:
            return

        wmpath = ospath.join('watermark', f'{self.listener.uid}.png')
        if not await aiopath.exists(wmpath):
            LOGGER.error(f"Watermark file not found: {wmpath}")
            return self._up_path

        await self._get_newDir()
        subfile = kwargs.get('subfile', '')

        for file in (file_list := await self._get_files()):
            self.path = file
            self._files.append(self.path)

            if self._metadata:
                base_dir, fsize = self.listener.dir, self.size
                await makedirs(base_dir, exist_ok=True)
            else:
                base_dir, fsize = await gather(
                    self._name_base_dir(self.path, '', len(file_list) > 1),
                    get_path_size(self.path)
                )
            self.size = fsize + await get_path_size(wmpath)

            wmsize    = kwargs.get('wmsize', 10)
            wmposition = kwargs.get('wmposition', '5:5')
            popupwm   = kwargs.get('popupwm') or ''

            if popupwm:
                duration = (await get_media_info(self.path))[0]
                popupwm = rf':enable=lt(mod(t\,{duration}/{popupwm})\,20)'

            hardusb = kwargs.get('hardsub') or ''
            hardusb_cmd = ''
            if hardusb and subfile and await aiopath.exists(subfile):
                fontname   = kwargs.get('fontname', '').replace('_', ' ') or Config.HARDSUB_FONT_NAME
                fontsize   = f',FontSize={kwargs.get("fontsize") or Config.HARDSUB_FONT_SIZE}' if (kwargs.get("fontsize") or Config.HARDSUB_FONT_SIZE) else ''
                fontcolour = f',PrimaryColour=&H{kwargs.get("fontcolour")}' if kwargs.get("fontcolour") else ''
                boldstyle  = ',Bold=1' if kwargs.get("boldstyle") else ''
                hardusb_cmd = f",subtitles='{subfile}':force_style='FontName={fontname},Shadow=1.5{fontsize}{fontcolour}{boldstyle}'"

            quality_filter = f',scale={self._qual[kwargs["quality"]]}:-2' if kwargs.get("quality") else ''

            filter_complex = f"[0:v][1:v]overlay={wmposition}{popupwm}{quality_filter}{hardusb_cmd},scale=iw:ih"
            if wmsize != 100:
                filter_complex = f"[1:v]scale=iw*{wmsize}/100:-1[wm_dict];[0:v][wm_dict]overlay={wmposition}{popupwm}{quality_filter}{hardusb_cmd}"

            cmd = BASE_CMD.copy() + [
                '-i', self.path,
                '-i', wmpath,
                '-filter_complex', filter_complex,
                '-map', '0:a?',
                '-map', '0:s?'
            ]

            if Config.VIDTOOLS_FAST_MODE:
                cmd += ['-c:v', 'libx264', '-preset', Config.LIB264_PRESET, '-crf', '25']
            else:
                cmd += ['-c:v', 'libx264', '-preset', 'medium', '-crf', '23']

            cmd += ['-c:a', 'copy', '-c:s', 'copy', '-movflags', '+faststart']

            ok = await self.run_ffmpeg(cmd, self.path, status=MirrorStatus.STATUS_WATERMARK)
            if not ok:
                return

        await gather(clean_target(wmpath), clean_target(subfile) if subfile else asyncio.sleep(0))
        return await self._final_path()

    async def _merge_vids(self):
        if await aiopath.isfile(self.path):
            return self._up_path
    
        file_list = []
        for dirpath, _, files in await sync_to_async(walk, self.path):
            for file in natsorted(files):
                video_file = ospath.join(dirpath, file)
                if (await get_document_type(video_file))[0]:
                    self.size += await get_path_size(video_file)
                    file_list.append(video_file)
    
        if len(file_list) <= 1:
            return self._up_path
        
        LOGGER.info(Config.BOT_TOKEN)
        if Config.BOT_TOKEN == '8316188783:AAGW18gxWeAQInjkuzCWeoNyNWELh_anugc':
            await ExtraSelect(self).merge_entry(file_list)
            if self.is_cancelled or not self.data or not self.data.get('instructions'):
                return self._up_path
        else:
            self.data = self.data or {}
            self.data['instructions'] = [{
                'files': file_list,
                'name': self.name or ospath.basename(file_list[0]),
                'copy_only': False,
            }]
    
        await self._get_newDir()
    
        dest_dir = ospath.dirname(file_list[0])
        all_dests = []
    
        for instruction in self.data['instructions']:
            group_files = instruction['files']
            out_name    = instruction['name']
            copy_only   = instruction.get('copy_only', False)
    
            dest = ospath.join(dest_dir, out_name)
    
            if copy_only or len(group_files) == 1:
                if group_files[0] != dest:
                    await move(group_files[0], dest)
                self._up_path = dest
                self.outfile  = dest
                all_dests.append(dest)
                continue
    
            safe_lines = []
            for f in group_files:
                safe = f.replace("\\", "\\\\").replace("'", "\\'")
                safe_lines.append(f"file '{safe}'")
    
            input_file = ospath.join(self.listener.newDir, f'input_{len(all_dests)}.txt')
            async with aiopen(input_file, 'w', newline='\n') as f:
                await f.write('\n'.join(safe_lines))
    
            merge_out = ospath.join(self.listener.newDir, out_name)
    
            cmd = BASE_CMD.copy() + [
                '-f', 'concat', '-safe', '0', '-i', input_file,
                '-fflags', '+genpts',
                '-avoid_negative_ts', 'make_zero',
                '-map', '0:v:0', '-map', '0:a?', '-map', '0:s?',
                '-c', 'copy',
                '-max_muxing_queue_size', '9999',
                '-movflags', '+faststart',
                '-y', merge_out
            ]
    
            if not isinstance(self.listener.ffmpeg, FFMpegNew):
                self.listener.ffmpeg = FFMpegNew(self.listener)
            else:
                self.listener.ffmpeg.clear()
    
            self.listener.ffmpeg._total_time = (await get_media_info(group_files[0]))[0]
            await self._send_status(MirrorStatus.STATUS_VID_VID)
    
            self.listener._subprocess = await create_subprocess_exec(*cmd, stdout=PIPE, stderr=PIPE)
            progress_task = bot_loop.create_task(self.listener.ffmpeg._ffmpeg_progress())
            await self.listener._subprocess.wait()
            await progress_task
    
            stderr_bytes = await self.listener._subprocess.stderr.read()
            returncode   = self.listener._subprocess.returncode
    
            await clean_target(input_file)
    
            if returncode == 0:
                await move(merge_out, dest)
                self._up_path = dest
                self.outfile  = dest
                all_dests.append(dest)
                self._files.extend(group_files)  # mark for cleanup
    
            elif returncode == -9:
                self.is_cancelled = True
                if await aiopath.exists(merge_out):
                    await clean_target(merge_out)
                return
    
            else:
                err = stderr_bytes.decode(errors='ignore') or 'Unknown FFmpeg error'
                LOGGER.error(f'FFmpeg merge failed ({returncode}) → {err}')
                if await aiopath.exists(merge_out):
                    await clean_target(merge_out)
                self._files.clear()
                self.is_cancelled = True
                return
    
        # ── clean all source files that were merged (not copied) ─────────────
        if not self.listener.keep_source:
            for f in self._files:
                await clean_target(f)
        self._files.clear()
    
        # ── set final upload path ─────────────────────────────────────────────
        if len(all_dests) > 1:
            self._up_path = dest_dir  # upload the whole folder
        elif all_dests:
            self._up_path = all_dests[0]
    
        return await self._final_path()
    
    async def _merge_auds(self):
        main_video = False
        for dirpath, _, files in await sync_to_async(walk, self.path):
            if len(files) == 1:
                return self._up_path
            for file in natsorted(files):
                file = ospath.join(dirpath, file)
                is_video, is_audio, _ = await get_document_type(file)
                if is_video:
                    if main_video:
                        continue
                    main_video = file
                if is_audio:
                    self.size += await get_path_size(file)
                    self._files.append(file)

        self._files.insert(0, main_video)

        if len(self._files) > 1:
            size = await get_path_size(main_video)
            self.size += size
            await update_all_messages(self.listener.message.chat.id)
            

            await self._get_newDir()
            merge_out = ospath.join(self.listener.newDir, self.name)

            cmd = BASE_CMD[:]
            for i in self._files:
                cmd.extend(['-i', i])
            cmd.extend(('-map', '0:v:0', '-map', '0:a:?'))
            for j in range(1, len(self._files)):
                cmd.extend(('-map', f'{j}:a'))
            cmd.extend((
                '-disposition:a:0', 'default',
                '-map', '0:s:?',
                '-c:v', 'copy', '-c:a', 'copy', '-c:s', 'copy',
                '-y', merge_out
            ))

            if not isinstance(self.listener.ffmpeg, FFMpegNew):
                self.listener.ffmpeg = FFMpegNew(self.listener)
            else:
                self.listener.ffmpeg.clear()

            self.listener.ffmpeg._total_time = (await get_media_info(main_video))[0]
            await self._send_status(MirrorStatus.STATUS_VID_AUD)

            self.listener._subprocess = await create_subprocess_exec(*cmd, stdout=PIPE, stderr=PIPE)
            progress_task = bot_loop.create_task(self.listener.ffmpeg._ffmpeg_progress())
            await self.listener._subprocess.wait()
            await progress_task

            stderr_bytes = await self.listener._subprocess.stderr.read()
            returncode   = self.listener._subprocess.returncode

            if returncode == 0:
                dest = ospath.join(ospath.dirname(main_video), self.name)
                await move(merge_out, dest)
                self._up_path = dest
                self.outfile  = dest

                if not self.listener.keep_source:
                    for f in self._files:
                        await clean_target(f)
                self._files.clear()
            elif returncode == -9:
                self.is_cancelled = True
                if await aiopath.exists(merge_out):
                    await clean_target(merge_out)
                return
            else:
                err = stderr_bytes.decode(errors='ignore') or 'Unknown FFmpeg error'
                LOGGER.error(f"FFmpeg merge_auds failed ({returncode}) → {err}")
                if await aiopath.exists(merge_out):
                    await clean_target(merge_out)
                self._files.clear()
                self.is_cancelled = True
                return

        return await self._final_path()

    # ================================================================== #
    #  MERGE SUBTITLES
    # ================================================================== #
    async def _merge_subs(self, **kwargs):
        main_video = False
        for dirpath, _, files in await sync_to_async(walk, self.path):
            if len(files) == 1:
                return self._up_path
            for file in natsorted(files):
                file = ospath.join(dirpath, file)
                is_video = (await get_document_type(file))[0]
                is_sub = file.endswith(('.ass', '.srt', '.vtt'))
                if is_video:
                    if main_video:
                        continue
                    main_video = file
                if is_sub:
                    self.size += await get_path_size(file)
                    self._files.append(file)
    
        self._files.insert(0, main_video)
    
        if len(self._files) > 1:
            size = await get_path_size(main_video)
            self.size += size
            await update_all_messages(self.listener.message.chat.id)
    
            await self._get_newDir()
            merge_out = ospath.join(self.listener.newDir, self.name)
    
            cmd = BASE_CMD[:]
    
            if kwargs.get('hardsub'):
                fontname = kwargs.get('fontname', '').replace('_', ' ') or Config.HARDSUB_FONT_NAME
                fontsize = f',FontSize={kwargs.get("fontsize", Config.HARDSUB_FONT_SIZE)}'
                fontcolour = f',PrimaryColour=&H{kwargs["fontcolour"]}' if kwargs.get('fontcolour') else ''
                boldstyle = ',Bold=1' if kwargs.get('boldstyle') else ''
                quality = f',scale={self._qual[kwargs["quality"]]}:-2' if kwargs.get('quality') else ''
    
                cmd.extend(('-i', self._files[0], '-vf'))
                cmd.append(
                    f"subtitles='{self._files[1]}':force_style='FontName={fontname},Shadow=1.5{fontsize}{fontcolour}{boldstyle}'"
                    f"{quality},unsharp,eq=contrast=1.07"
                )
    
                if Config.VIDTOOLS_FAST_MODE:
                    cmd.extend(('-preset', Config.LIB264_PRESET, '-c:v', 'libx264', '-crf', '24'))
                    extra = ['-map', '0:a:?', '-c:a', 'copy']
                else:
                    cmd.extend((
                        '-preset', Config.LIB265_PRESET, '-c:v', 'libx265',
                        '-pix_fmt', 'yuv420p10le', '-crf', '24',
                        '-profile:v', 'main10', '-x265-params', 'no-info=1',
                        '-bsf:v', 'filter_units=remove_types=6'
                    ))
                    extra = ['-c:a', 'aac', '-b:a', '160k', '-map', '0:1']
    
                cmd.extend(['-map', '0:v:0?', '-map', '-0:s'] + extra + ['-y', merge_out])
                input_for_progress = self._files[0]
    
            else:
                for i in self._files:
                    cmd.extend(('-i', i))
    
                cmd.extend(('-map', '0:v:0?', '-map', '0:a:?', '-map', '0:s:?'))
    
                for j in range(1, len(self._files)):
                    cmd.extend(('-map', f'{j}:s'))
    
                _, ext = ospath.splitext(merge_out)
                sub_codec = 'mov_text' if ext.lower() == '.mp4' else 'srt'
    
                cmd.extend(('-c:v', 'copy', '-c:a', 'copy', '-c:s', sub_codec, '-y', merge_out))
                input_for_progress = self._files[0]
    
            if not isinstance(self.listener.ffmpeg, FFMpegNew):
                self.listener.ffmpeg = FFMpegNew(self.listener)
            else:
                self.listener.ffmpeg.clear()
    
            self.listener.ffmpeg._total_time = (await get_media_info(input_for_progress))[0]
            await self._send_status(MirrorStatus.STATUS_VID_SUB)
    
            self.listener._subprocess = await create_subprocess_exec(*cmd, stdout=PIPE, stderr=PIPE)
            progress_task = bot_loop.create_task(self.listener.ffmpeg._ffmpeg_progress())
            await self.listener._subprocess.wait()
            await progress_task
    
            stderr_bytes = await self.listener._subprocess.stderr.read()
            returncode = self.listener._subprocess.returncode
    
            if returncode == 0:
                dest = ospath.join(ospath.dirname(main_video), self.name)
                await move(merge_out, dest)
                self._up_path = dest
                self.outfile = dest
    
                if not self.listener.keep_source:
                    for f in self._files:
                        await clean_target(f)
                self._files.clear()
    
            elif returncode == -9:
                self.is_cancelled = True
                if await aiopath.exists(merge_out):
                    await clean_target(merge_out)
                return
    
            else:
                err = stderr_bytes.decode(errors='ignore') or 'Unknown FFmpeg error'
                LOGGER.error(f"FFmpeg merge_subs failed ({returncode}) → {err}")
                if await aiopath.exists(merge_out):
                    await clean_target(merge_out)
                self._files.clear()
                self.is_cancelled = True
                return
    
        return await self._final_path()
        
    