import re
from contextlib import suppress
from secrets import token_hex
from PIL import Image
from math import ceil
from hashlib import md5
from aiofiles.os import remove, path as aiopath, makedirs
from aiofiles import open as aiopen
import json
from asyncio import (
    create_subprocess_exec,
    gather,
    wait_for,
    sleep,
)
from asyncio.subprocess import PIPE
from os import path as ospath, replace as osreplace
from re import search as re_search, escape
from time import time
from aioshutil import rmtree
from langcodes import Language
from io import BytesIO

from ... import LOGGER, cpu_no, DOWNLOAD_DIR
from ...core.config_manager import BinConfig
from .bot_utils import cmd_exec, sync_to_async, new_task
from .fs_utils import get_mime_type, is_archive, is_archive_split, clean_target
from bot.helper.utils import time_to_seconds
from bot.helper.utils import request, resolve_position


import json
import subprocess

QUAL_MAP = {
    480: 480,
    540: 540,
    720: 720,
    1080: 1080,
    2160: 2160,
    4320: 4320,
    8640: 8640,
}

async def AddPhotoWatermark(image, user_id, user_dict):
    try:
        #LOGGER.info(f"[WM-PREVIEW] Start | user_id={user_id} | file={image}")

        if not user_dict.get("WM_ENABLE"):
            #LOGGER.info("[WM-PREVIEW] Watermark disabled")
            return image

        wm_type = user_dict.get("WM_TYPE")
        if wm_type not in ("text", "image"):
            #LOGGER.warning(f"[WM-PREVIEW] Invalid WM_TYPE: {wm_type}")
            return image

        out_path = ospath.join("watermark", f"{user_id}.jpg")
        await clean_target(out_path)

        posx, posy = resolve_position(user_dict)
        #LOGGER.info(f"[WM-PREVIEW] Position resolved → x={posx}, y={posy}")

        cmd = [
            BinConfig.FFMPEG_NAME,
            "-hide_banner",
            "-loglevel", "error",
            "-y",
            "-i", image
        ]

        filters = []

        if wm_type == "text":
            text = (user_dict.get("WM_TEXT") or "").strip()
            if not text:
                #LOGGER.warning("[WM-PREVIEW] Empty text watermark")
                return image

            text = text.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:")
            fontsize = int(user_dict.get("WM_FONTSIZE") or 24)
            color = user_dict.get("WM_FONTCOLOR", "white")
            opacity = float(user_dict.get("WM_OPACITY") or 0.85)

            filters.append(
                f"[0:v]drawtext=text='{text}':x={posx}:y={posy}:"
                f"fontsize={fontsize}:fontcolor={color}@{opacity}[outv]"
            )

        else:
            wm_img = user_dict.get("WM_IMAGE")
            if not wm_img or not await aiopath.exists(wm_img):
                #LOGGER.error(f"[WM-PREVIEW] Watermark image missing → {wm_img}")
                return image

            cmd.extend(["-i", wm_img])

            opacity = float(user_dict.get("WM_OPACITY", 1.0))
            filters.append("[1:v]scale='min(200,iw)':-2[wm]")

            if opacity < 1.0:
                filters.append(f"[wm]format=rgba,colorchannelmixer=aa={opacity}[wmf]")
                wm_pad = "[wmf]"
            else:
                wm_pad = "[wm]"

            filters.append(f"[0:v]{wm_pad}overlay=x={posx}:y={posy}:format=auto[outv]")

        cmd.extend([
            "-filter_complex", ";".join(filters),
            "-map", "[outv]",
            "-frames:v", "1",
            "-c:v", "mjpeg",
            "-pix_fmt", "yuvj420p",
            "-q:v", "3",
            out_path
        ])

        #LOGGER.info(f"[WM-PREVIEW] FFmpeg CMD → {' '.join(cmd)}")

        stdout, stderr, code = await cmd_exec(cmd)

        #LOGGER.info(f"[WM-PREVIEW] Return code={code}")
        if stderr:
            LOGGER.error(f"[WM-PREVIEW] STDERR → {stderr}")

        if code != 0 or not await aiopath.exists(out_path):
            #LOGGER.error("[WM-PREVIEW] Failed to create preview watermark")
            return image

        #LOGGER.info(f"[WM-PREVIEW] Success → {out_path}")
        return out_path

    except Exception:
        LOGGER.exception("[WM-PREVIEW] Fatal exception")
        return image
        
async def get_subtitle_streams(streams):
    subs = []
    for s in streams:
        if s.get('codec_type') == 'subtitle':
            subs.append({
                'index': s['index'],
                'lang': s.get('tags', {}).get('language', 'unknown'),
                'codec': s.get('codec_name')
            })
    return subs
    
async def merge_images_multi(images, out_dir):
    LOGGER.error(f"[MERGE] INPUT images={images}")

    sheets = []
    images = images[:30]

    for i in range(0, len(images), 10):
        opened = []
        for p in images[i:i + 10]:
            try:
                opened.append(Image.open(p).convert("RGB"))
            except Exception as e:
                LOGGER.error(f"[MERGE] OPEN FAIL {p} | {e}")

        if not opened:
            LOGGER.error("[MERGE] EMPTY BATCH")
            continue

        W, pad = 640, 6
        resized = []
        for img in opened:
            w, h = img.size
            resized.append(img.resize((W, int(h * W / w)), Image.LANCZOS))

        cols = 2
        rows = ceil(len(resized) / cols)

        row_heights = [
            max(img.height for img in resized[r * cols:(r + 1) * cols])
            for r in range(rows)
        ]

        sheet_w = cols * W + pad * (cols + 1)
        sheet_h = sum(row_heights) + pad * (rows + 1)

        sheet = Image.new("RGB", (sheet_w, sheet_h), (0, 0, 0))

        y = pad
        idx = 0
        for r in range(rows):
            x = pad
            for _ in range(cols):
                if idx >= len(resized):
                    break
                sheet.paste(resized[idx], (x, y))
                x += W + pad
                idx += 1
            y += row_heights[r] + pad

        out = ospath.join(out_dir, f"sheet_{len(sheets) + 1}.jpg")
        sheet.save(out, "JPEG", quality=95)
        sheets.append(out)

        LOGGER.error(f"[MERGE] CREATED {out}")

        for img in opened:
            img.close()

    return sheets

def get_md5_hash(up_path):
    md5_hash = md5()
    with open(up_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            md5_hash.update(byte_block)
        return md5_hash.hexdigest()

async def create_thumb(msg, _id=""):
    if not _id:
        _id = time()
        path = f"{DOWNLOAD_DIR}thumbnails"
    else:
        path = "thumbnails"
    await makedirs(path, exist_ok=True)
    photo_dir = await msg.download()
    output = ospath.join(path, f"{_id}.jpg")
    await sync_to_async(Image.open(photo_dir).convert("RGB").save, output, "JPEG")
    await remove(photo_dir)
    return output

async def get_media_info(path, extra_info=False):
    try:
        result = await cmd_exec(
            [
                "ffprobe",
                "-hide_banner",
                "-loglevel",
                "error",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                path,
            ]
        )
    except Exception as e:
        LOGGER.error(f"Get Media Info: {e}. Mostly File not found! - File: {path}")
        return (0, "", "", "") if extra_info else (0, None, None)
    if result[0] and result[2] == 0:
        ffresult = eval(result[0])
        fields = ffresult.get("format")
        if fields is None:
            LOGGER.error(f"get_media_info: {result}")
            return (0, "", "", "") if extra_info else (0, None, None)
        duration = round(float(fields.get("duration", 0)))
        if extra_info:
            lang, qual, stitles = "", "", ""
            if (streams := ffresult.get("streams")) and streams[0].get("codec_type") == "video":
                qual = int(streams[0].get("height"))
                qual = f"{next((v for k, v in QUAL_MAP.items() if qual <= k), qual)}p"
                for stream in streams:
                    if stream.get("codec_type") == "audio" and (lc := stream.get("tags", {}).get("language")):
                        with suppress(Exception):
                            lc = Language.get(lc).display_name('en')
                        if lc not in lang:
                            lang += f"{lc}, "
                    if stream.get("codec_type") == "subtitle" and (st := stream.get("tags", {}).get("language")):
                        with suppress(Exception):
                            st = Language.get(st).display_name('en')
                        if st not in stitles:
                            stitles += f"{st}, "
            return duration, qual, lang[:-2], stitles[:-2]
        tags = fields.get("tags", {})
        artist = tags.get("artist") or tags.get("ARTIST") or tags.get("Artist")
        title = tags.get("title") or tags.get("TITLE") or tags.get("Title")
        return duration, artist, title
    return (0, "", "", "") if extra_info else (0, None, None)


async def get_document_type(path):
    is_video, is_audio, is_image = False, False, False
    if (
        is_archive(path)
        or is_archive_split(path)
        or re_search(r".+(\.|_)(rar|7z|zip|bin)(\.0*\d+)?$", path)
    ):
        return is_video, is_audio, is_image
    mime_type = await sync_to_async(get_mime_type, path)
    if mime_type.startswith("image"):
        return False, False, True
    try:
        result = await cmd_exec(
            [
                "ffprobe",
                "-hide_banner",
                "-loglevel",
                "error",
                "-print_format",
                "json",
                "-show_streams",
                path,
            ]
        )
        if result[1] and mime_type.startswith("video"):
            is_video = True
    except Exception as e:
        LOGGER.error(f"Get Document Type: {e}. Mostly File not found! - File: {path}")
        if mime_type.startswith("audio"):
            return False, True, False
        if not mime_type.startswith("video") and not mime_type.endswith("octet-stream"):
            return is_video, is_audio, is_image
        if mime_type.startswith("video"):
            is_video = True
        return is_video, is_audio, is_image
    if result[0] and result[2] == 0:
        fields = eval(result[0]).get("streams")
        if fields is None:
            LOGGER.error(f"get_document_type: {result}")
            return is_video, is_audio, is_image
        is_video = False
        for stream in fields:
            if stream.get("codec_type") == "video":
                codec_name = stream.get("codec_name", "").lower()
                if codec_name not in {"mjpeg", "png", "bmp"}:
                    is_video = True
            elif stream.get("codec_type") == "audio":
                is_audio = True
    return is_video, is_audio, is_image


async def get_streams(file):
    """
    Gets media stream information using ffprobe.

    Args:
        file: Path to the media file.

    Returns:
        A list of stream objects (dictionaries) or None if an error occurs
        or no streams are found.
    """
    cmd = [
        "ffprobe",
        "-hide_banner",
        "-loglevel",
        "error",
        "-print_format",
        "json",
        "-show_streams",
        file,
    ]
    process = await create_subprocess_exec(*cmd, stdout=PIPE, stderr=PIPE)
    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        LOGGER.error(f"Error getting stream info: {stderr.decode().strip()}")
        return None

    try:
        return json.loads(stdout)["streams"]
    except KeyError:
        LOGGER.error(
            f"No streams found in the ffprobe output: {stdout.decode().strip()}",
        )
        return None


async def take_ss_old(video_file, ss_nb):
    duration = (await get_media_info(video_file))[0]
    if not duration or ss_nb <= 0:
        return False

    dirpath, name = video_file.rsplit("/", 1)
    name, _ = ospath.splitext(name)
    dirpath = f"{dirpath}/{name}_mltbss"
    await makedirs(dirpath, exist_ok=True)

    skip = max(int(duration * 0.05), 1)
    usable = max(duration - (skip * 2), 1)

    interval = usable / ss_nb
    timestamps = [skip + int(interval * i) for i in range(ss_nb)]

    cmds = []
    for i, ts in enumerate(timestamps):
        output = f"{dirpath}/SS.{name}_{i:02}.png"
        cmd = [
            BinConfig.FFMPEG_NAME,
            "-hide_banner",
            "-loglevel", "error",
            "-ss", str(ts),
            "-i", video_file,
            "-frames:v", "1",
            "-q:v", "2",
            "-threads", f"{max(1, cpu_no // 2)}",
            output,
        ]
        cmds.append(cmd_exec(cmd))

    try:
        results = await wait_for(gather(*cmds), timeout=120)
        for _, stderr, code in results:
            if code != 0:
                await rmtree(dirpath, ignore_errors=True)
                return False
    except Exception:
        await rmtree(dirpath, ignore_errors=True)
        return False

    return dirpath

async def take_ss(video_file, ss_nb) -> bool:
    duration = (await get_media_info(video_file))[0]
    if duration != 0:
        dirpath, name = video_file.rsplit("/", 1)
        name, _ = ospath.splitext(name)
        dirpath = f"{dirpath}/{name}_mltbss"
        await makedirs(dirpath, exist_ok=True)
        interval = duration // (ss_nb + 1)
        cap_time = interval
        cmds = []
        for i in range(ss_nb):
            output = f"{dirpath}/SS.{name}_{i:02}.png"
            cmd = [
                BinConfig.FFMPEG_NAME,
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                f"{cap_time}",
                "-i",
                video_file,
                "-q:v",
                "1",
                "-frames:v",
                "1",
                "-threads",
                f"{max(1, cpu_no // 2)}",
                output,
            ]
            cap_time += interval
            cmds.append(cmd_exec(cmd))
        try:
            resutls = await wait_for(gather(*cmds), timeout=60)
            if resutls[0][2] != 0:
                LOGGER.error(
                    f"Error while creating sreenshots from video. Path: {video_file}. stderr: {resutls[0][1]}"
                )
                await rmtree(dirpath, ignore_errors=True)
                return False
        except Exception:
            LOGGER.error(
                f"Error while creating sreenshots from video. Path: {video_file}. Error: Timeout some issues with ffmpeg with specific arch!"
            )
            await rmtree(dirpath, ignore_errors=True)
            return False
        return dirpath
    else:
        LOGGER.error("take_ss: Can't get the duration of video")
        return False
        
async def get_audio_thumbnail(audio_file):
    output_dir = f"{DOWNLOAD_DIR}thumbnails"
    await makedirs(output_dir, exist_ok=True)
    output = ospath.join(output_dir, f"{time()}.jpg")
    cmd = [
        BinConfig.FFMPEG_NAME,
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        audio_file,
        "-an",
        "-vcodec",
        "copy",
        "-threads",
        f"{max(1, cpu_no // 2)}",
        output,
    ]
    try:
        _, err, code = await wait_for(cmd_exec(cmd), timeout=60)
        if code != 0 or not await aiopath.exists(output):
            LOGGER.error(
                f"Error while extracting thumbnail from audio. Name: {audio_file} stderr: {err}"
            )
            return None
    except Exception:
        LOGGER.error(
            f"Error while extracting thumbnail from audio. Name: {audio_file}. Error: Timeout some issues with ffmpeg with specific arch!"
        )
        return None
    return output


async def get_video_thumbnail(video_file, duration, auto_thumbnail=None):
    if auto_thumbnail:
        file_name = ospath.basename(video_file)
        if thumb:= await get_auto_thumb(file_name):
            return thumb
    output_dir = f"{DOWNLOAD_DIR}thumbnails"
    await makedirs(output_dir, exist_ok=True)
    output = ospath.join(output_dir, f"{time()}.jpg")
    if duration is None:
        duration = (await get_media_info(video_file))[0]
    if duration == 0:
        duration = 3
    duration = duration // 2
    cmd = [
        BinConfig.FFMPEG_NAME,
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{duration}",
        "-i",
        video_file,
        "-vf",
        "scale=640:-1",
        "-q:v",
        "5",
        "-vframes",
        "1",
        "-threads",
        "1",
        output,
    ]
    try:
        _, err, code = await wait_for(cmd_exec(cmd), timeout=60)
        if code != 0 or not await aiopath.exists(output):
            LOGGER.error(
                f"Error while extracting thumbnail from video. Name: {video_file} stderr: {err}"
            )
            return None
    except Exception:
        LOGGER.error(
            f"Error while extracting thumbnail from video. Name: {video_file}. Error: Timeout some issues with ffmpeg with specific arch!"
        )
        return None
    return output

async def get_multiple_frames_thumbnail(video_file, layout, keep_screenshots):
    layout = re.sub(r"(\d+)\D+(\d+)", r"\1x\2", layout)
    ss_nb = layout.split("x")
    if len(ss_nb) != 2 or not ss_nb[0].isdigit() or not ss_nb[1].isdigit():
        LOGGER.error(f"Invalid layout value: {layout}")
        return None
    ss_nb = int(ss_nb[0]) * int(ss_nb[1])
    if ss_nb == 0:
        LOGGER.error(f"Invalid layout value: {layout}")
        return None
    dirpath = await take_ss(video_file, ss_nb)
    if not dirpath:
        return None
    output_dir = f"{DOWNLOAD_DIR}thumbnails"
    await makedirs(output_dir, exist_ok=True)
    output = ospath.join(output_dir, f"{time()}.jpg")
    cmd = [
        BinConfig.FFMPEG_NAME,
        "-hide_banner",
        "-loglevel",
        "error",
        "-pattern_type",
        "glob",
        "-i",
        f"{escape(dirpath)}/*.png",
        "-vf",
        f"tile={layout}, thumbnail",
        "-q:v",
        "1",
        "-frames:v",
        "1",
        "-f",
        "mjpeg",
        "-threads",
        f"{max(1, cpu_no // 2)}",
        output,
    ]
    try:
        _, err, code = await wait_for(cmd_exec(cmd), timeout=60)
        if code != 0 or not await aiopath.exists(output):
            LOGGER.error(
                f"Error while combining thumbnails for video. Name: {video_file} stderr: {err}"
            )
            return None
    except Exception:
        LOGGER.error(
            f"Error while combining thumbnails from video. Name: {video_file}. Error: Timeout some issues with ffmpeg with specific arch!"
        )
        return None
    finally:
        if not keep_screenshots:
            await rmtree(dirpath, ignore_errors=True)
    return output


class FFMpeg:
    def __init__(self, listener):
        self._listener = listener
        self._processed_bytes = 0
        self._last_processed_bytes = 0
        self._processed_time = 0
        self._last_processed_time = 0
        self._speed_raw = 0
        self._progress_raw = 0
        self._total_time = 0
        self._eta_raw = 0
        self._time_rate = 0.1
        self._start_time = 0
        
    
    @property
    def processed_bytes(self):
        return self._processed_bytes

    @property
    def speed_raw(self):
        return self._speed_raw

    @property
    def progress_raw(self):
        return self._progress_raw

    @property
    def eta_raw(self):
        return self._eta_raw

    def clear(self):
        self._start_time = time()
        self._processed_bytes = 0
        self._processed_time = 0
        self._speed_raw = 0
        self._progress_raw = 0
        self._eta_raw = 0
        self._time_rate = 0.1
        self._last_processed_time = 0
        self._last_processed_bytes = 0

    
    async def _ffmpeg_progress(self):
        while not (
            self._listener._subprocess.returncode is not None
            or self._listener.is_cancelled
            or self._listener._subprocess.stdout.at_eof()
        ):
            try:
                line = await wait_for(self._listener._subprocess.stdout.readline(), 60)
            except Exception:
                break
            line = line.decode().strip()
            if not line:
                break
            if "=" in line:
                key, value = line.split("=", 1)
                if value != "N/A":
                    if key == "total_size":
                        self._processed_bytes = int(value) + self._last_processed_bytes
                        self._speed_raw = self._processed_bytes / (
                            time() - self._start_time
                        )
                    elif key == "speed":
                        self._time_rate = max(0.1, float(value.strip("x")))
                    elif key == "out_time":
                        self._processed_time = (
                            time_to_seconds(value) + self._last_processed_time
                        )
                        try:
                            self._progress_raw = (
                                self._processed_time * 100
                            ) / self._total_time
                            if (
                                hasattr(self._listener, "subsize")
                                and self._listener.subsize
                                and self._progress_raw > 0
                            ):
                                self._processed_bytes = int(
                                    self._listener.subsize * (self._progress_raw / 100)
                                )
                            if (time() - self._start_time) > 0:
                                self._speed_raw = self._processed_bytes / (
                                    time() - self._start_time
                                )
                            else:
                                self._speed_raw = 0
                            self._eta_raw = (
                                self._total_time - self._processed_time
                            ) / self._time_rate
                        except ZeroDivisionError:
                            self._progress_raw = 0
                            self._eta_raw = 0
            await sleep(0.05)

    @new_task
    async def ffmpeg_cmds(self, ffmpeg, f_path):
        self.clear()
        self._total_time = (await get_media_info(f_path))[0]
        base_name, ext = ospath.splitext(f_path)
        dir, base_name = base_name.rsplit("/", 1)
        indices = [
            index
            for index, item in enumerate(ffmpeg)
            if item.startswith("mltb") or item == "mltb"
        ]
        outputs = []
        for index in indices:
            output_file = ffmpeg[index]
            if output_file != "mltb" and output_file.startswith("mltb"):
                bo, oext = ospath.splitext(output_file)
                if oext:
                    if ext == oext:
                        prefix = f"ffmpeg{index}." if bo == "mltb" else ""
                    else:
                        prefix = ""
                    ext = ""
                else:
                    prefix = ""
            else:
                prefix = f"ffmpeg{index}."
            output = f"{dir}/{prefix}{output_file.replace('mltb', base_name)}{ext}"
            outputs.append(output)
            ffmpeg[index] = output
        if self._listener.is_cancelled:
            return False
        self._listener._subprocess = await create_subprocess_exec(
            *ffmpeg, stdout=PIPE, stderr=PIPE
        )
        await self._ffmpeg_progress()
        _, stderr = await self._listener._subprocess.communicate()
        code = self._listener._subprocess.returncode
        if self._listener.is_cancelled:
            return False
        if code == 0:
            return outputs
        elif code == -9:
            self._listener.is_cancelled = True
            return False
        else:
            try:
                stderr = stderr.decode().strip()
            except Exception:
                stderr = "Unable to decode the error!"
            LOGGER.error(
                f"{stderr}. Something went wrong while running ffmpeg cmd, mostly file requires different/specific arguments. Path: {f_path}"
            )
            for op in outputs:
                if await aiopath.exists(op):
                    await remove(op)
            return False

    async def convert_video(self, video_file, ext, retry=False):
        self.clear()
        self._total_time = (await get_media_info(video_file))[0]
        base_name = ospath.splitext(video_file)[0]
        output = f"{base_name}.{ext}"
        if retry:
            cmd = [
                BinConfig.FFMPEG_NAME,
                "-hide_banner",
                "-loglevel",
                "error",
                "-progress",
                "pipe:1",
                "-i",
                video_file,
                "-map",
                "0",
                "-c:v",
                "libx264",
                "-c:a",
                "aac",
                "-threads",
                f"{max(1, cpu_no // 2)}",
                output,
            ]
            if ext == "mp4":
                cmd[14:14] = ["-c:s", "mov_text"]
            elif ext == "mkv":
                cmd[14:14] = ["-c:s", "ass"]
            else:
                cmd[14:14] = ["-c:s", "copy"]
        else:
            cmd = [
                BinConfig.FFMPEG_NAME,
                "-hide_banner",
                "-loglevel",
                "error",
                "-progress",
                "pipe:1",
                "-i",
                video_file,
                "-map",
                "0",
                "-c",
                "copy",
                "-threads",
                f"{max(1, cpu_no // 2)}",
                output,
            ]
        if self._listener.is_cancelled:
            return False
        self._listener._subprocess = await create_subprocess_exec(
            *cmd, stdout=PIPE, stderr=PIPE
        )
        await self._ffmpeg_progress()
        _, stderr = await self._listener._subprocess.communicate()
        code = self._listener._subprocess.returncode
        if self._listener.is_cancelled:
            return False
        if code == 0:
            return output
        elif code == -9:
            self._listener.is_cancelled = True
            return False
        else:
            if await aiopath.exists(output):
                await remove(output)
            if not retry:
                return await self.convert_video(video_file, ext, True)
            try:
                stderr = stderr.decode().strip()
            except Exception:
                stderr = "Unable to decode the error!"
            LOGGER.error(
                f"{stderr}. Something went wrong while converting video, mostly file need specific codec. Path: {video_file}"
            )
        return False

    async def convert_audio(self, audio_file, ext):
        self.clear()
        self._total_time = (await get_media_info(audio_file))[0]
        base_name = ospath.splitext(audio_file)[0]
        output = f"{base_name}.{ext}"
        cmd = [
            BinConfig.FFMPEG_NAME,
            "-hide_banner",
            "-loglevel",
            "error",
            "-progress",
            "pipe:1",
            "-i",
            audio_file,
            "-threads",
            f"{max(1, cpu_no // 2)}",
            output,
        ]
        if self._listener.is_cancelled:
            return False
        self._listener._subprocess = await create_subprocess_exec(
            *cmd, stdout=PIPE, stderr=PIPE
        )
        await self._ffmpeg_progress()
        _, stderr = await self._listener._subprocess.communicate()
        code = self._listener._subprocess.returncode
        if self._listener.is_cancelled:
            return False
        if code == 0:
            return output
        elif code == -9:
            self._listener.is_cancelled = True
            return False
        else:
            try:
                stderr = stderr.decode().strip()
            except Exception:
                stderr = "Unable to decode the error!"
            LOGGER.error(
                f"{stderr}. Something went wrong while converting audio, mostly file need specific codec. Path: {audio_file}"
            )
            if await aiopath.exists(output):
                await remove(output)
        return False

    async def sample_video(self, video_file, sample_duration, part_duration):
        self.clear()
        self._total_time = sample_duration
        dir, name = video_file.rsplit("/", 1)
        output_file = f"{dir}/SAMPLE.{name}"
        segments = [(0, part_duration)]
        duration = (await get_media_info(video_file))[0]
        remaining_duration = duration - (part_duration * 2)
        parts = (sample_duration - (part_duration * 2)) // part_duration
        time_interval = remaining_duration // parts
        next_segment = time_interval
        for _ in range(parts):
            segments.append((next_segment, next_segment + part_duration))
            next_segment += time_interval
        segments.append((duration - part_duration, duration))

        filter_complex = ""
        for i, (start, end) in enumerate(segments):
            filter_complex += (
                f"[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS[v{i}]; "
            )
            filter_complex += (
                f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS[a{i}]; "
            )

        for i in range(len(segments)):
            filter_complex += f"[v{i}][a{i}]"

        filter_complex += f"concat=n={len(segments)}:v=1:a=1[vout][aout]"

        cmd = [
            BinConfig.FFMPEG_NAME,
            "-hide_banner",
            "-loglevel",
            "error",
            "-progress",
            "pipe:1",
            "-i",
            video_file,
            "-filter_complex",
            filter_complex,
            "-map",
            "[vout]",
            "-map",
            "[aout]",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-threads",
            f"{max(1, cpu_no // 2)}",
            output_file,
        ]

        if self._listener.is_cancelled:
            return False
        self._listener._subprocess = await create_subprocess_exec(
            *cmd, stdout=PIPE, stderr=PIPE
        )
        await self._ffmpeg_progress()
        _, stderr = await self._listener._subprocess.communicate()
        code = self._listener._subprocess.returncode
        if self._listener.is_cancelled:
            return False
        if code == -9:
            self._listener.is_cancelled = True
            return False
        elif code == 0:
            return output_file
        else:
            try:
                stderr = stderr.decode().strip()
            except Exception:
                stderr = "Unable to decode the error!"
            LOGGER.error(
                f"{stderr}. Something went wrong while creating sample video, mostly file is corrupted. Path: {video_file}"
            )
            if await aiopath.exists(output_file):
                await remove(output_file)
            return False

    async def split(self, f_path, file_, parts, split_size):
        self.clear()
        multi_streams = True
        self._total_time = duration = (await get_media_info(f_path))[0]
        base_name, extension = ospath.splitext(file_)
        split_size -= 3000000
        start_time = 0
        i = 1
        while i <= parts or start_time < duration - 4:
            out_path = ospath.join(ospath.dirname(f_path), f"{base_name}.part{i:03}{extension}")
            cmd = [
                BinConfig.FFMPEG_NAME,
                "-hide_banner",
                "-loglevel",
                "error",
                "-progress",
                "pipe:1",
                "-ss",
                str(start_time),
                "-i",
                f_path,
                "-fs",
                str(split_size),
                "-map",
                "0",
                "-map_chapters",
                "-1",
                "-async",
                "1",
                "-strict",
                "-2",
                "-c",
                "copy",
                "-threads",
                f"{max(1, cpu_no // 2)}",
                out_path,
            ]
            if not multi_streams:
                del cmd[12]
                del cmd[12]
            if self._listener.is_cancelled:
                return False
            self._listener._subprocess = await create_subprocess_exec(
                *cmd, stdout=PIPE, stderr=PIPE
            )
            await self._ffmpeg_progress()
            _, stderr = await self._listener._subprocess.communicate()
            code = self._listener._subprocess.returncode
            if self._listener.is_cancelled:
                return False
            if code == -9:
                self._listener.is_cancelled = True
                return False
            elif code != 0:
                try:
                    stderr = stderr.decode().strip()
                except Exception:
                    stderr = "Unable to decode the error!"
                with suppress(Exception):
                    await remove(out_path)
                if multi_streams:
                    LOGGER.warning(
                        f"{stderr}. Retrying without map, -map 0 not working in all situations. Path: {f_path}"
                    )
                    multi_streams = False
                    continue
                else:
                    LOGGER.warning(
                        f"{stderr}. Unable to split this video, if it's size less than {self._listener.max_split_size} will be uploaded as it is. Path: {f_path}"
                    )
                return False
            out_size = await aiopath.getsize(out_path)
            if out_size > self._listener.max_split_size:
                split_size -= (out_size - self._listener.max_split_size) + 5000000
                LOGGER.warning(
                    f"Part size is {out_size}. Trying again with lower split size!. Path: {f_path}"
                )
                await remove(out_path)
                continue
            lpd = (await get_media_info(out_path))[0]
            if lpd == 0:
                LOGGER.error(
                    f"Something went wrong while splitting, mostly file is corrupted. Path: {f_path}"
                )
                break
            elif duration == lpd:
                LOGGER.warning(
                    f"This file has been splitted with default stream and audio, so you will only see one part with less size from orginal one because it doesn't have all streams and audios. This happens mostly with MKV videos. Path: {f_path}"
                )
                break
            elif lpd <= 3:
                await remove(out_path)
                break
            self._last_processed_time += lpd
            self._last_processed_bytes += out_size
            start_time += lpd - 3
            i += 1
        return True

class FFMpegNew:
    def __init__(self, listener):
        self._listener = listener
        self._processed_bytes = 0
        self._last_processed_bytes = 0
        self._processed_time = 0
        self._last_processed_time = 0
        self._speed_raw = 0
        self._progress_raw = 0
        self._total_time = 0
        self._eta_raw = 0
        self._time_rate = 0.1
        self._start_time = 0
        
    
    @property
    def processed_bytes(self):
        return self._processed_bytes

    @property
    def speed_raw(self):
        return self._speed_raw

    @property
    def progress_raw(self):
        return self._progress_raw

    @property
    def eta_raw(self):
        return self._eta_raw

    def clear(self):
        self._start_time = time()  # ✅ Set immediately
        self._processed_bytes = 0
        self._processed_time = 0
        self._speed_raw = 0
        self._progress_raw = 0
        self._eta_raw = 0
        self._time_rate = 0.1
        self._last_processed_time = 0
        self._last_processed_bytes = 0
        self._total_time = 0  # ✅ Reset total time too

    
    async def _ffmpeg_progress(self):
        proc = self._listener._subprocess
    
        last_size = 0
        last_time = time()
        self._start_time = time()  # ✅ Initialize start time here
    
        while True:
            if proc is None:
                break
            if self._listener.is_cancelled:
                break
            if proc.returncode is not None:
                break
    
            try:
                line = await wait_for(proc.stdout.readline(), 30)
            except Exception:
                break
    
            if not line:
                await sleep(0.1)
                continue
    
            line = line.decode(errors="ignore").strip()
    
            if "=" not in line:
                continue
    
            key, value = line.split("=", 1)
    
            if value == "N/A":
                continue
    
            now = time()
    
            # ✅ encoding progress (watermark, compress, convert)
            if key == "out_time":
                try:
                    self._processed_time = time_to_seconds(value)
    
                    if self._total_time > 0:
                        self._progress_raw = (
                            self._processed_time / self._total_time
                        ) * 100
    
                    if self._listener.size:
                        self._processed_bytes = int(
                            self._listener.size * (self._progress_raw / 100)
                        )
                        
                        # ✅ Calculate speed for encoding mode
                        if self._time_rate > 0.1 and self._total_time > 0:
                            self._speed_raw = (
                                self._listener.size / self._total_time
                            ) * self._time_rate
    
                except:
                    pass
    
            # ✅ copy / concat progress
            elif key == "total_size":
                try:
                    current_size = int(value)
    
                    if self._listener.size:
                        self._processed_bytes = current_size
                        self._progress_raw = (
                            current_size / self._listener.size
                        ) * 100
    
                    # smooth speed calculation
                    delta = current_size - last_size
                    dt = now - last_time
    
                    if dt > 0:
                        self._speed_raw = delta / dt
    
                    last_size = current_size
                    last_time = now
    
                except:
                    pass
    
            # fallback speed rate from ffmpeg
            elif key == "speed":
                try:
                    self._time_rate = max(0.1, float(value.strip("x")))
                except:
                    pass
    
            # ✅ FIX: ETA calculation (works for both modes)
            if self._progress_raw > 0 and self._progress_raw < 100:
                elapsed = now - self._start_time
                
                # Method 1: Based on progress percentage (most reliable)
                remaining = elapsed * (100 - self._progress_raw) / self._progress_raw
                self._eta_raw = remaining
                
            elif self._speed_raw > 0 and self._listener.size:
                # Method 2: Based on speed (fallback)
                remaining_bytes = self._listener.size - self._processed_bytes
                if remaining_bytes > 0:
                    self._eta_raw = remaining_bytes / self._speed_raw
            else:
                self._eta_raw = 0  # ✅ Prevent garbage values
    
            await sleep(0.05)
    