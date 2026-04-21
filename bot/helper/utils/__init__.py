import aiohttp

from asyncio import sleep, TimeoutError



async def request(url, method="GET", **kwargs):
    try:
        timeout = aiohttp.ClientTimeout(total=7)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.request(method, url, **kwargs) as resp:

                if resp.status != 200:
                    return None

                try:
                    return await resp.json(content_type=None)
                except Exception:
                    return None

    except (aiohttp.ClientError, TimeoutError):
        return None
    except Exception:
        return None

def resolve_position(wm):
    margin = int(wm.get("WM_MARGIN") or 10)
    raw = str(wm.get("WM_POSITION", "C")).strip().upper()
    wm_type = wm.get("WM_TYPE", "text")

    if wm_type == "text":
        W, H = "W", "H"
        w, h = "text_w", "text_h"
    else:
        W, H = "main_w", "main_h"
        w, h = "overlay_w", "overlay_h"

    grid = {
        "TL": (f"{margin}", f"{margin}"),
        "TC": (f"({W}-{w})/2", f"{margin}"),
        "TR": (f"{W}-{w}-{margin}", f"{margin}"),

        "ML": (f"{margin}", f"({H}-{h})/2"),
        "C":  (f"({W}-{w})/2", f"({H}-{h})/2"),
        "MR": (f"{W}-{w}-{margin}", f"({H}-{h})/2"),

        "BL": (f"{margin}", f"{H}-{h}-{margin}"),
        "BC": (f"({W}-{w})/2", f"{H}-{h}-{margin}"),
        "BR": (f"{W}-{w}-{margin}", f"{H}-{h}-{margin}")
    }

    if raw in grid:
        return grid[raw]

    parts = raw.split()
    if len(parts) == 2:
        return parts[0], parts[1]
    if len(parts) == 1:
        return parts[0], "0"

    return grid["C"]

def is_media(message):
    if not message:
        return
    return (message.document or message.photo or message.video or message.audio or message.voice
            or message.video_note or message.sticker or message.animation or None)

def get_readable_time(seconds: int):
    periods = [("d", 86400), ("h", 3600), ("m", 60), ("s", 1)]
    result = ""
    for period_name, period_seconds in periods:
        if seconds >= period_seconds:
            period_value, seconds = divmod(seconds, period_seconds)
            result += f"{int(period_value)}{period_name}"
    return result

def time_to_seconds(time_duration):
    try:
        parts = time_duration.split(":")
        if len(parts) == 3:
            hours, minutes, seconds = map(float, parts)
        elif len(parts) == 2:
            hours = 0
            minutes, seconds = map(float, parts)
        elif len(parts) == 1:
            hours = 0
            minutes = 0
            seconds = float(parts[0])
        else:
            return 0
        return hours * 3600 + minutes * 60 + seconds
    except Exception:
        return 0

def get_readable_file_size(size_in_bytes):
    if not size_in_bytes:
        return "0B"

    index = 0
    while size_in_bytes >= 1024 and index < len(SIZE_UNITS) - 1:
        size_in_bytes /= 1024
        index += 1

    return f"{size_in_bytes:.2f}{SIZE_UNITS[index]}"


encode_dict = {
    "360p": {
        "crf": "30",
        "audio_bitrate": "35k",
        "resolution": "640x360",
        "preset": "veryfast",
        "video_codec": "libx264",
        "audio_codec": "libopus",
        "pixel_format": "yuv420p",
    },
    "480p": {
        "crf": "28",
        "audio_bitrate": "64k",
        "resolution": "854x480",
        "preset": "veryfast",
        "video_codec": "libx264",
        "audio_codec": "libopus",
        "pixel_format": "yuv420p",
    },
    "720pHEVC": {
        "crf": "25",
        "audio_bitrate": "128k",
        "resolution": "1280x720",
        "preset": "medium",
        "video_codec": "libx265",
        "audio_codec": "libopus",
        "pixel_format": "yuv420p",
    },
    "720p": {
        "crf": "23",
        "audio_bitrate": "128k",
        "resolution": "1280x720",
        "preset": "medium",
        "video_codec": "libx264",
        "audio_codec": "libopus",
        "pixel_format": "yuv420p",
    },
    "1080pHEVC": {
        "crf": "22",
        "audio_bitrate": "192k",
        "resolution": "1920x1080",
        "preset": "medium",
        "video_codec": "libx265",
        "audio_codec": "libopus",
        "pixel_format": "yuv420p",
    },
    "custom": {},
}

wm_dict = {
    'WM_TYPE': None,
    'WM_POSITION': 'TL',
    'WM_MARGIN': 10,
    'WM_OPACITY': 1.0,
    'WM_ENABLE': False,
    'WM_THUMB': False,
    
    'WM_TEXT': '',
    'WM_FONTFILE': '',
    'WM_FONTSIZE': 24,
    'WM_FONTCOLOR': 'white',

    'WM_IMAGE': None,
    'WM_IMAGEX': -1,
    'WM_IMAGEY': -1,
}
