from html import escape as html_escape
from hashlib import md5
from time import strftime, gmtime, time
from re import IGNORECASE, sub as re_sub, search as re_search
from shlex import split as ssplit
from natsort import natsorted
from os import path as ospath
from aiofiles.os import remove as aioremove, path as aiopath, mkdir, makedirs, listdir
from aioshutil import rmtree as aiormtree
from contextlib import suppress
from asyncio import create_subprocess_exec, create_task, gather, Semaphore
from asyncio.subprocess import PIPE
from telegraph import upload_file
from langcodes import Language

from bot import bot_cache, LOGGER, MAX_SPLIT_SIZE, config_dict, user_data
from bot.modules.mediainfo import parseinfo
from bot.helper.ext_utils.bot_utils import cmd_exec, sync_to_async, get_readable_file_size, get_readable_time
from bot.helper.ext_utils.fs_utils import ARCH_EXT, get_mime_type
from bot.helper.ext_utils.telegraph_helper import telegraph


async def is_multi_streams(path):
    try:
        result = await cmd_exec(["ffprobe", "-hide_banner", "-loglevel", "error", "-print_format",
                                 "json", "-show_streams", path])
        if res := result[1]:
            LOGGER.warning(f'Get Video Streams: {res}')
    except Exception as e:
        LOGGER.error(f'Get Video Streams: {e}. Mostly File not found!')
        return False
    fields = eval(result[0]).get('streams')
    if fields is None:
        LOGGER.error(f"get_video_streams: {result}")
        return False
    videos = 0
    audios = 0
    for stream in fields:
        if stream.get('codec_type') == 'video':
            videos += 1
        elif stream.get('codec_type') == 'audio':
            audios += 1
    return videos > 1 or audios > 1


async def get_media_info(path, metadata=False):
    try:
        result = await cmd_exec(["ffprobe", "-hide_banner", "-loglevel", "error", "-print_format",
                                 "json", "-show_format", "-show_streams", path])
        if res := result[1]:
            LOGGER.warning(f'Media Info FF: {res}')
    except Exception as e:
        LOGGER.error(f'Media Info: {e}. Mostly File not found!')
        return (0, "", "", "") if metadata else (0, None, None)
    ffresult = eval(result[0])
    fields = ffresult.get('format')
    if fields is None:
        LOGGER.error(f"Media Info Sections: {result}")
        return (0, "", "", "") if metadata else (0, None, None)
    duration = round(float(fields.get('duration', 0)))
    if metadata:
        lang, qual, stitles = "", "", ""
        if (streams := ffresult.get('streams')) and streams[0].get('codec_type') == 'video':
            qual = int(streams[0].get('height'))
            qual = f"{480 if qual <= 480 else 540 if qual <= 540 else 720 if qual <= 720 else 1080 if qual <= 1080 else 2160 if qual <= 2160 else 4320 if qual <= 4320 else 8640}p"
            for stream in streams:
                if stream.get('codec_type') == 'audio' and (lc := stream.get('tags', {}).get('language')):
                    with suppress(Exception):
                        lc = Language.get(lc).display_name()
                    if lc not in lang:
                        lang += f"{lc}, "
                if stream.get('codec_type') == 'subtitle' and (st := stream.get('tags', {}).get('language')):
                    with suppress(Exception):
                        st = Language.get(st).display_name()
                    if st not in stitles:
                        stitles += f"{st}, "
        return duration, qual, lang[:-2], stitles[:-2]
    tags = fields.get('tags', {})
    artist = tags.get('artist') or tags.get('ARTIST') or tags.get("Artist")
    title = tags.get('title') or tags.get('TITLE') or tags.get("Title")
    return duration, artist, title


async def get_document_type(path):
    is_video, is_audio, is_image = False, False, False
    if path.endswith(tuple(ARCH_EXT)) or re_search(r'.+(\.|_)(rar|7z|zip|bin)(\.0*\d+)?$', path):
        return is_video, is_audio, is_image
    mime_type = await sync_to_async(get_mime_type, path)
    if mime_type.startswith('audio'):
        return False, True, False
    if mime_type.startswith('image'):
        return False, False, True
    if not mime_type.startswith('video') and not mime_type.endswith('octet-stream'):
        return is_video, is_audio, is_image
    try:
        result = await cmd_exec(["ffprobe", "-hide_banner", "-loglevel", "error", "-print_format",
                                 "json", "-show_streams", path])
        if res := result[1]:
            LOGGER.warning(f'Get Document Type: {res}')
    except Exception as e:
        LOGGER.error(f'Get Document Type: {e}. Mostly File not found!')
        return is_video, is_audio, is_image
    fields = eval(result[0]).get('streams')
    if fields is None:
        LOGGER.error(f"get_document_type: {result}")
        return is_video, is_audio, is_image
    for stream in fields:
        if stream.get('codec_type') == 'video':
            is_video = True
        elif stream.get('codec_type') == 'audio':
            is_audio = True
    return is_video, is_audio, is_image


async def get_audio_thumb(audio_file):
    des_dir = 'Thumbnails'
    if not await aiopath.exists(des_dir):
        await mkdir(des_dir)
    des_dir = ospath.join(des_dir, f"{time()}.jpg")
    cmd = [bot_cache['pkgs'][2], "-hide_banner", "-loglevel", "error",
           "-i", audio_file, "-an", "-vcodec", "copy", des_dir]
    status = await create_subprocess_exec(*cmd, stderr=PIPE)
    if await status.wait() != 0 or not await aiopath.exists(des_dir):
        err = (await status.stderr.read()).decode().strip()
        LOGGER.error(
            f'Error while extracting thumbnail from audio. Name: {audio_file} stderr: {err}')
        return None
    return des_dir


async def take_ss(video_file, duration=None, total=1, gen_ss=False):
    des_dir = ospath.join('Thumbnails', f"{time()}")
    await makedirs(des_dir, exist_ok=True)
    if duration is None:
        duration = (await get_media_info(video_file))[0]
    if duration == 0:
        duration = 3
    duration = duration - (duration * 2 / 100)
    cmd = [bot_cache['pkgs'][2], "-hide_banner", "-loglevel", "error", "-ss", "",
           "-i", video_file, "-vf", "thumbnail", "-frames:v", "1", des_dir]
    tstamps = {}
    thumb_sem = Semaphore(3)
    
    async def extract_ss(eq_thumb):
        async with thumb_sem:
            cmd[5] = str((duration // total) * eq_thumb)
            tstamps[f"wz_thumb_{eq_thumb}.jpg"] = strftime("%H:%M:%S", gmtime(float(cmd[5])))
            cmd[-1] = ospath.join(des_dir, f"wz_thumb_{eq_thumb}.jpg")
            task = await create_subprocess_exec(*cmd, stderr=PIPE)
            return (task, await task.wait(), eq_thumb)
    
    tasks = [extract_ss(eq_thumb) for eq_thumb in range(1, total+1)]
    status = await gather(*tasks)
    
    for task, rtype, eq_thumb in status:
        if rtype != 0 or not await aiopath.exists(ospath.join(des_dir, f"wz_thumb_{eq_thumb}.jpg")):
            err = (await task.stderr.read()).decode().strip()
            LOGGER.error(f'Error while extracting thumbnail no. {eq_thumb} from video. Name: {video_file} stderr: {err}')
            await aiormtree(des_dir)
            return None
    return (des_dir, tstamps) if gen_ss else ospath.join(des_dir, "wz_thumb_1.jpg")


async def split_file(path, size, file_, dirpath, split_size, listener, start_time=0, i=1, inLoop=False, multi_streams=True):
    if listener.suproc == 'cancelled' or listener.suproc is not None and listener.suproc.returncode == -9:
        return False
    if listener.seed and not listener.newDir:
        dirpath = f"{dirpath}/splited_files_mltb"
        if not await aiopath.exists(dirpath):
            await mkdir(dirpath)
    user_id = listener.message.from_user.id
    user_dict = user_data.get(user_id, {})
    leech_split_size = user_dict.get(
        'split_size') or config_dict['LEECH_SPLIT_SIZE']
    parts = -(-size // leech_split_size)
    if (user_dict.get('equal_splits') or config_dict['EQUAL_SPLITS'] and 'equal_splits' not in user_dict) and not inLoop:
        split_size = ((size + parts - 1) // parts) + 1000
    if (await get_document_type(path))[0]:
        if multi_streams:
            multi_streams = await is_multi_streams(path)
        duration = (await get_media_info(path))[0]
        base_name, extension = ospath.splitext(file_)
        split_size -= 5000000
        while i <= parts or start_time < duration - 4:
            parted_name = f"{base_name}.part{i:03}{extension}"
            out_path = ospath.join(dirpath, parted_name)
            cmd = [bot_cache['pkgs'][2], "-hide_banner", "-loglevel", "error", "-ss", str(start_time), "-i", path,
                   "-fs", str(split_size), "-map", "0", "-map_chapters", "-1", "-async", "1", "-strict",
                   "-2", "-c", "copy", out_path]
            if not multi_streams:
                del cmd[10]
                del cmd[10]
            if listener.suproc == 'cancelled' or listener.suproc is not None and listener.suproc.returncode == -9:
                return False
            listener.suproc = await create_subprocess_exec(*cmd, stderr=PIPE)
            code = await listener.suproc.wait()
            if code == -9:
                return False
            elif code != 0:
                err = (await listener.suproc.stderr.read()).decode().strip()
                try:
                    await aioremove(out_path)
                except Exception:
                    pass
                if multi_streams:
                    LOGGER.warning(
                        f"{err}. Retrying without map, -map 0 not working in all situations. Path: {path}")
                    return await split_file(path, size, file_, dirpath, split_size, listener, start_time, i, True, False)
                else:
                    LOGGER.warning(
                        f"{err}. Unable to split this video, if it's size less than {MAX_SPLIT_SIZE} will be uploaded as it is. Path: {path}")
                return "errored"
            out_size = await aiopath.getsize(out_path)
            if out_size > MAX_SPLIT_SIZE:
                dif = out_size - MAX_SPLIT_SIZE
                split_size -= dif + 5000000
                await aioremove(out_path)
                return await split_file(path, size, file_, dirpath, split_size, listener, start_time, i, True, )
            lpd = (await get_media_info(out_path))[0]
            if lpd == 0:
                LOGGER.error(
                    f'Something went wrong while splitting, mostly file is corrupted. Path: {path}')
                break
            elif duration == lpd:
                LOGGER.warning(
                    f"This file has been splitted with default stream and audio, so you will only see one part with less size from orginal one because it doesn't have all streams and audios. This happens mostly with MKV videos. Path: {path}")
                break
            elif lpd <= 3:
                await aioremove(out_path)
                break
            start_time += lpd - 3
            i += 1
    else:
        out_path = ospath.join(dirpath, f"{file_}.")
        listener.suproc = await create_subprocess_exec("split", "--numeric-suffixes=1", "--suffix-length=3",
                                                       f"--bytes={split_size}", path, out_path, stderr=PIPE)
        code = await listener.suproc.wait()
        if code == -9:
            return False
        elif code != 0:
            err = (await listener.suproc.stderr.read()).decode().strip()
            LOGGER.error(err)
    return True
# ================== RDX AUTO RENAME HELPERS ==================
_RDX_LANGS = [
    "Hindi", "English", "Bhojpuri", "Bangla", "Bengali", "Tamil", "Telugu",
    "Malayalam", "Kannada", "Marathi", "Punjabi", "Urdu", "Korean", "Japanese"
]
_RDX_OTT = {"NF", "AMZN", "DSNP", "HMAX", "ATVP", "ZEE5", "SONY", "AHA", "VOOT", "TG"}
_RDX_QUAL = ["WEB-DL", "WEBRip", "BluRay", "HDRip", "DVDRip", "CAM"]
_RDX_RES = ["480p", "720p", "1080p", "1440p", "2160p", "4K"]
_RDX_LIB = ["x264", "x265", "HEVC", "AVC", "AV1"]
_RDX_SUB = ["ESub", "MSub", "HSub", "Sub"]

def _rdx_parse_fields(raw_filename: str) -> dict:
    name_only, ext = ospath.splitext(raw_filename)
    ext = ext.lower()

    text = name_only

    # Generic website/source remover
    # Examples: www.1TamilMV.LTD, Vegamovies.is, HDHub4u, MoviesMod, MovieVerse, BollyFlix etc.
    text = re_sub(
        r'\b(?:www\.)?[a-z0-9][a-z0-9-]*'
        r'(?:movies?|movie|flix|hub|mod|mv|hd|web|dl|rip|ott|cinema|verse|world|zone|mart|wap|links?|drive|cloud|series)'
        r'[a-z0-9-]*\.(?:com|net|org|in|cc|co|xyz|lol|ltd|is|tv|to|me|info|site|live|pro|dev|foo)\b',
        ' ',
        text,
        flags=IGNORECASE
    )
    text = re_sub(
        r'\b\d*[a-z0-9]*'
        r'(?:movies?|movie|flix|hub|mod|mv|hd|web|dl|rip|ott|cinema|verse|world|zone|mart|wap|links?|drive|cloud|series)'
        r'[a-z0-9]*\b',
        ' ',
        text,
        flags=IGNORECASE
    )
    text = re_sub(
        r'\b(com|net|org|in|cc|co|xyz|lol|ltd|is|tv|to|me|info|site|live|pro|dev|foo)\b',
        ' ',
        text,
        flags=IGNORECASE
    )
    text = re_sub(r'\b(www|frl|rls|source|original|untouched)\b', ' ', text, flags=IGNORECASE)

    # Normalize separators/brackets for parsing
    search_text = text.replace('.', ' ').replace('_', ' ').replace('-', ' ')
    search_text = re_sub(r'[\[\]\(\)\{\},+]', ' ', search_text)
    search_text = re_sub(r'\s+', ' ', search_text).strip()

    # Season / Episode: S05E01, S05 E01
    season = episode = ''
    m = re_search(r'\bS\s*(\d{1,2})\s*(?:E|EP)\s*(\d{1,3})\b', search_text, IGNORECASE)
    if m:
        season = f"S{int(m.group(1)):02d}"
        episode = f"E{int(m.group(2)):02d}"

    # Year
    ym = re_search(r'\b(19\d{2}|20\d{2})\b', search_text)
    year = ym.group(1) if ym else ''

    # Resolution
    rm = re_search(r'\b(480|540|720|1080|1440|2160|4320)p\b|\b4K\b', search_text, IGNORECASE)
    resolution = f"{rm.group(1)}p" if rm and rm.group(1) else ('4K' if rm else '')

    # Quality
    quality = ''
    for q in ['SDTV-Rip', 'HDTV-Rip', 'SDTVRip', 'HDTVRip', 'SDTV', 'HDTV', 'DVDScr', 'PRE-HD', 'WEBDL', 'WEB-DL', 'WEB DL', 'WEBRip', 'BluRay', 'HDRip', 'PreDVD', 'DVDRip', 'YTRip', 'HDTS', 'HDTC', 'CAMRip', 'HQSprint', 'HDCAMRip', 'HDCAM', 'TELESYNC', 'TSQRip', 'BRRip', 'HQ SPrint', 'HQ HDRip', 'CAM']:
        q_pattern = re_sub('-', r'[- ]?', q)
        if re_search(rf'\b{q_pattern}\b', search_text, IGNORECASE):
            quality = 'HDRip' if q == 'HQ HDRip' else 'WEB-DL' if q in ['WEBDL', 'WEB DL'] else q
            break

    # OTT / Source
    ott = ''
    for o in ['NF', 'AMZN', 'HBO', 'JioHotstar', 'JioHS', 'JHS', 'DSNP', 'HS', 'CR', 'JC', 'Jio', 'PF', 'VOD', 'BMS', 'CRAV', 'MX', 'ATVP', 'MAX', 'PCOK', 'SONYLiv', 'ZEE5', 'SS', 'APLVTV', 'HULU', 'APL', 'YT', 'STZ', 'STARZ', 'PS', 'AHA', 'HMAX', 'VOOT', 'TG']:
        if re_search(rf'\b{o}\b', search_text, IGNORECASE):
            ott = o
            break

    # Codec library
    lib = ''
    lm = re_search(r'\b(x264|x265|HEVC|AVC|AV1|H\.264|H\.265)\b', search_text, IGNORECASE)
    if lm:
        lib = lm.group(1).replace('H.264', 'x264').replace('H.265', 'x265')

    # Audio
    audio = ''
    am = re_search(r'\b(DD\+?5\.1|DDP5\.1|DDP\d?(?:\.\d)?|AAC|8CH|6CH|2CH|5\.1|7\.1|2\.0|ATMOS)\b', search_text, IGNORECASE)
    if am:
        audio = am.group(1).upper()

    # Subtitle short
    shortsub = ''
    for ssub in ['ESub', 'MSub', 'HSub', 'Sub']:
        if re_search(rf'\b{ssub}\b', search_text, IGNORECASE):
            shortsub = ssub
            break

    # Languages, including short forms
    lang_map = {
        # Indian languages
        'hindi': 'Hindi', 'hin': 'Hindi', 'hi': 'Hindi',
        'english': 'English', 'eng': 'English', 'en': 'English',
        'bhojpuri': 'Bhojpuri',
        'bangla': 'Bangla', 'bengali': 'Bangla', 'ben': 'Bangla', 'bn': 'Bangla',
        'tamil': 'Tamil', 'tam': 'Tamil', 'ta': 'Tamil',
        'telugu': 'Telugu', 'tel': 'Telugu', 'te': 'Telugu',
        'malayalam': 'Malayalam', 'mal': 'Malayalam', 'ml': 'Malayalam',
        'kannada': 'Kannada', 'kan': 'Kannada', 'kn': 'Kannada',
        'marathi': 'Marathi', 'mar': 'Marathi', 'mr': 'Marathi',
        'punjabi': 'Punjabi', 'pan': 'Punjabi', 'pa': 'Punjabi',
        'urdu': 'Urdu', 'ur': 'Urdu',
        'gujarati': 'Gujarati', 'guj': 'Gujarati', 'gu': 'Gujarati',
        'odia': 'Odia', 'oriya': 'Odia', 'or': 'Odia',
        'assamese': 'Assamese', 'asm': 'Assamese', 'as': 'Assamese',
        'sanskrit': 'Sanskrit', 'san': 'Sanskrit', 'sa': 'Sanskrit',

        # Asian languages
        'chinese': 'Chinese', 'chi': 'Chinese', 'zh': 'Chinese',
        'mandarin': 'Chinese', 'cantonese': 'Chinese',
        'korean': 'Korean', 'kor': 'Korean', 'ko': 'Korean',
        'japanese': 'Japanese', 'jpn': 'Japanese', 'ja': 'Japanese',
        'thai': 'Thai', 'tha': 'Thai', 'th': 'Thai',
        'indonesian': 'Indonesian', 'ind': 'Indonesian', 'id': 'Indonesian',
        'malay': 'Malay', 'msa': 'Malay', 'ms': 'Malay',
        'vietnamese': 'Vietnamese', 'vie': 'Vietnamese', 'vi': 'Vietnamese',
        'filipino': 'Filipino', 'tagalog': 'Filipino', 'tl': 'Filipino',

        # European languages
        'french': 'French', 'fre': 'French', 'fra': 'French', 'fr': 'French',
        'spanish': 'Spanish', 'spa': 'Spanish', 'es': 'Spanish',
        'german': 'German', 'ger': 'German', 'deu': 'German', 'de': 'German',
        'italian': 'Italian', 'ita': 'Italian', 'it': 'Italian',
        'portuguese': 'Portuguese', 'por': 'Portuguese', 'pt': 'Portuguese',
        'russian': 'Russian', 'rus': 'Russian', 'ru': 'Russian',
        'turkish': 'Turkish', 'tur': 'Turkish', 'tr': 'Turkish',
        'dutch': 'Dutch', 'nld': 'Dutch', 'nl': 'Dutch',
        'polish': 'Polish', 'pol': 'Polish', 'pl': 'Polish',
        'swedish': 'Swedish', 'swe': 'Swedish', 'sv': 'Swedish',
        'norwegian': 'Norwegian', 'nor': 'Norwegian', 'no': 'Norwegian',
        'danish': 'Danish', 'dan': 'Danish', 'da': 'Danish',
        'finnish': 'Finnish', 'fin': 'Finnish', 'fi': 'Finnish',
        'greek': 'Greek', 'ell': 'Greek', 'el': 'Greek',

        # Middle East / others
        'arabic': 'Arabic', 'ara': 'Arabic', 'ar': 'Arabic',
        'persian': 'Persian', 'farsi': 'Persian', 'fa': 'Persian',
        'hebrew': 'Hebrew', 'heb': 'Hebrew', 'he': 'Hebrew',
    }
    langs = []
    for k, v in lang_map.items():
        if re_search(rf'\b{k}\b', search_text, IGNORECASE) and v not in langs:
            langs.append(v)
    languages = ' '.join(langs)

    if len(langs) == 1:
        shortlang = langs[0]
    elif len(langs) == 2:
        shortlang = 'Dual'
    elif len(langs) > 2:
        shortlang = f'Multi{len(langs)}'
    else:
        shortlang = ''

    # Part name
    part = ''
    pm = re_search(r'\bP(\d{2})\b|\.part0*(\d+)', search_text, IGNORECASE)
    if pm:
        part_no = pm.group(1) or pm.group(2)
        part = f"P{int(part_no):02d}"

    # Clean title only
    title = search_text
    remove_patterns = [
        r'\b(19\d{2}|20\d{2})\b',
        r'\bS\s*\d{1,2}\s*(?:E|EP)\s*\d{1,3}\b',
        r'\b(480|540|720|1080|1440|2160|4320)p\b',
        r'\b4K\b',
        r'\bWEB[- ]?DL\b',
        r'\bWEBDL\b',
        r'\bSDTV[- ]?Rip\b',
        r'\bHDTV[- ]?Rip\b',
        r'\bSDTVRip\b',
        r'\bHDTVRip\b',
        r'\bSDTV\b',
        r'\bDVDScr\b',
        r'\bPRE[- ]?HD\b',
        r'\bWEB DL\b',
        r'\bWEBRip\b',
        r'\bHQ\b',
        r'\bHDRip\b',
        r'\bBluRay\b',
        r'\bBRRip\b',
        r'\bDVDRip\b',
        r'\bHDTV\b',
        r'\bCAMRip\b',
        r'\bHQSprint\b',
        r'\bHQ SPrint\b',
        r'\bHDCAMRip\b',
        r'\bHDCAM\b',
        r'\bTELESYNC\b',
        r'\bTSQRip\b',
        r'\bYTRip\b',
        r'\bHDTS\b',
        r'\bHDTC\b',
        r'\bPreDVD\b',
        r'\bCAM\b',
        r'\b(NF|AMZN|HBO|JioHotstar|JioHS|JHS|DSNP|HS|CR|JC|Jio|PF|VOD|BMS|CRAV|MX|ATVP|MAX|PCOK|SONYLiv|ZEE5|SS|APLVTV|HULU|APL|YT|STZ|STARZ|PS|AHA|HMAX|VOOT|TG)\b',
        r'\b(x264|x265|HEVC|AVC|AV1|H\.264|H\.265)\b',
        r'\b(DD\+?5\.1|DDP5\.1|DDP\d?(?:\.\d)?|AAC|8CH|6CH|2CH|5\.1|7\.1|2\.0|ATMOS)\b',
        r'\b\d+(?:\.\d+)?\s*(GB|MB|KB)\b',
        r'\b\d+\s*Kbps\b',
        r'\b(ESub|MSub|HSub|Sub)\b',
    ]
    for pat in remove_patterns:
        title = re_sub(pat, ' ', title, flags=IGNORECASE)

    for lg in sorted(lang_map.keys(), key=len, reverse=True):
        title = re_sub(rf'\b{lg}\b', ' ', title, flags=IGNORECASE)

    # Remove broken leftovers like Hi / 2 0 / 5 1
    title = re_sub(r'\b(Hi|Hin|Eng|En|Tam|Tel|Mal|Kan|Ml|Kn|Te|Ta|Chi|Zh|Kor|Ko|Jpn|Ja|Tha|Th|Ind|Id|Vie|Vi|Fre|Fra|Fr|Spa|Es|Ger|Deu|De|Rus|Ru|Ara|Ar|Gu|Guj|Ben|Bn|Mar|Mr|Pan|Pa|Por|Pt|Ita|It|Tur|Tr|Nld|Nl|Swe|Sv|Nor|No|Dan|Da|Fin|Fi)\b', ' ', title, flags=IGNORECASE)
    title = re_sub(r'\b\d\s+\d\b', ' ', title)
    title = re_sub(r'\s*\+\s*', ' ', title)
    title = re_sub(r'\s+', ' ', title).strip(' -._')

    return {
        'RDX': raw_filename,
        'file_name': raw_filename,
        'filename': raw_filename,
        'raw_name': name_only,
        'extension': ext,
        'name': title,
        'year': year,
        'resolution': resolution,
        'quality': quality,
        'ott': ott,
        'season': season,
        'episode': episode,
        'audio': audio,
        'lib': lib,
        'languages': languages,
        'subtitles': '',
        'shortsub': shortsub,
        'shortlang': shortlang,
        'part': part,
        'duration': '',
        'file_size': '',
    }


def _rdx_apply_template(tpl: str, meta: dict) -> str:
    # safe, only {key} tokens. Unknown tokens left as-is.
    def repl(m):
        k = m.group(1)
        v = meta.get(k, m.group(0))
        return str(v) if v is not None else ""
    out = re_sub(r"\{([a-zA-Z0-9_]+)\}", repl, tpl)
    out = re_sub(r"\s+", " ", out).strip()
    return out

def _rdx_sanitize_filename(name: str) -> str:
    # remove forbidden filename chars (safe for most FS)
    name = re_sub(r'[\\/:*?"<>|]+', " ", name)
    name = re_sub(r"\s+", " ", name).strip()
    return name
# ============================================================


async def format_filename(file_, user_id, dirpath=None, isMirror=False):
    user_dict = user_data.get(user_id, {})
    ftag, ctag = ('m', 'MIRROR') if isMirror else ('l', 'LEECH')
    prefix = config_dict[f'{ctag}_FILENAME_PREFIX'] if (val:=user_dict.get(f'{ftag}prefix', '')) == '' else val
    remname = config_dict[f'{ctag}_FILENAME_REMNAME'] if (val:=user_dict.get(f'{ftag}remname', '')) == '' else val
    suffix = config_dict[f'{ctag}_FILENAME_SUFFIX'] if (val:=user_dict.get(f'{ftag}suffix', '')) == '' else val
    lcaption = config_dict['LEECH_FILENAME_CAPTION'] if (val:=user_dict.get('lcaption', '')) == '' else val
    auto_rename = user_dict.get('auto_rename', '')
 
    prefile_ = file_
    #file_ = re_sub(r'www\S+', '', file_)
    
    # Remove URLs starting with "www"
    file_ = re_sub(r'www\S+', '', file_, flags=IGNORECASE)

    # ----- AUTO RENAME (filename) -----
    # Remove leading/trailing dashes and extra spaces
    # file_ = re_sub(r'^\s*-\s*', '', file_)
    file_ = re_sub(r'(^\s*-\s*|(\s*-\s*){2,})', '', file_)
        
    # --- Auto Rename Template Apply (Filename) ---
    if auto_rename and isinstance(auto_rename, str) and auto_rename.strip():
        _meta = _rdx_parse_fields(prefile_)
        _meta["extension"] = _meta.get("extension", ospath.splitext(prefile_)[1].lower())

        # GK-style media metadata merge via ffprobe.
        # Uses actual video stream tags for languages/subtitles/resolution/duration/size when available.
        if dirpath:
            up_path = ospath.join(dirpath, prefile_)
            if await aiopath.exists(up_path):
                try:
                    dur, qual, lang, subs = await get_media_info(up_path, True)
                    if qual:
                        _meta["resolution"] = qual
                    if lang:
                        _langs = [x.strip() for x in lang.split(",") if x.strip()]
                        _meta["languages"] = ' '.join(_langs)
                        if len(_langs) == 1:
                            _meta["shortlang"] = _langs[0]
                        elif len(_langs) == 2:
                            _meta["shortlang"] = "Dual"
                        elif len(_langs) > 2:
                            _meta["shortlang"] = f"Multi{len(_langs)}"
                    if subs:
                        _meta["subtitles"] = subs
                        _subs = [x.strip() for x in subs.split(",") if x.strip()]
                        _meta["shortsub"] = "MSub" if len(_subs) > 1 else "ESub"
                    if dur:
                        _meta["duration"] = get_readable_time(dur)
                    _meta["file_size"] = get_readable_file_size(await aiopath.getsize(up_path))
                except Exception as e:
                    LOGGER.warning(f"Auto Rename MediaInfo failed for {up_path}: {e}")

        _new_base = _rdx_apply_template(auto_rename, _meta)
        _new_base = _rdx_sanitize_filename(_new_base)
        ext_ = ospath.splitext(prefile_)[1]
        if ext_ and not _new_base.lower().endswith(ext_.lower()):
            _new_base = _new_base + ext_
        if _new_base:
            file_ = _new_base

        
    if remname:
        if not remname.startswith('|'):
            remname = f"|{remname}"
        remname = remname.replace('\s', ' ')
        slit = remname.split("|")
        __newFileName = ospath.splitext(file_)[0]
        for rep in range(1, len(slit)):
            args = slit[rep].split(":")
            if len(args) == 3:
                __newFileName = re_sub(args[0], args[1], __newFileName, int(args[2]))
            elif len(args) == 2:
                __newFileName = re_sub(args[0], args[1], __newFileName)
            elif len(args) == 1:
                __newFileName = re_sub(args[0], '', __newFileName)
        file_ = __newFileName + ospath.splitext(file_)[1]
        LOGGER.info(f"New Remname : {file_}")

    nfile_ = file_
    if prefix:
        nfile_ = prefix.replace('\s', ' ') + file_
        prefix = re_sub(r'<.*?>', '', prefix).replace('\s', ' ')
        if not file_.startswith(prefix):
            file_ = f"{prefix}{file_}"

    if suffix and not isMirror:
        suffix = suffix.replace('\s', ' ')
        sufLen = len(suffix)
        fileDict = file_.split('.')
        _extIn = 1 + len(fileDict[-1])
        _extOutName = '.'.join(
            fileDict[:-1]).replace('.', ' ').replace('-', ' ')
        _newExtFileName = f"{_extOutName}{suffix}.{fileDict[-1]}"
        if len(_extOutName) > (64 - (sufLen + _extIn)):
            _newExtFileName = (
                _extOutName[: 64 - (sufLen + _extIn)]
                + f"{suffix}.{fileDict[-1]}"
            )
        file_ = _newExtFileName
    elif suffix:
        suffix = suffix.replace('\s', ' ')
        file_ = f"{ospath.splitext(file_)[0]}{suffix}{ospath.splitext(file_)[1]}" if '.' in file_ else f"{file_}{suffix}"


    cap_mono =  f"<{config_dict['CAP_FONT']}>{nfile_}</{config_dict['CAP_FONT']}>" if config_dict['CAP_FONT'] else nfile_
    if lcaption and dirpath and not isMirror:
        
        def lowerVars(match):
            return f"{{{match.group(1).lower()}}}"

        lcaption = lcaption.replace('\|', '%%').replace('\{', '&%&').replace('\}', '$%$').replace('\s', ' ')
        slit = lcaption.split("|")
        slit[0] = re_sub(r'\{([^}]+)\}', lowerVars, slit[0])
        up_path = ospath.join(dirpath, prefile_)
        dur, qual, lang, subs = await get_media_info(up_path, True)
        cap_mono = slit[0].format(
            filename = nfile_,
            size = get_readable_file_size(await aiopath.getsize(up_path)),
            duration = get_readable_time(dur),
            quality = qual,
            languages = lang,
            subtitles = subs,
            md5_hash = get_md5_hash(up_path)
        )
        if len(slit) > 1:
            for rep in range(1, len(slit)):
                args = slit[rep].split(":")
                if len(args) == 3:
                    cap_mono = cap_mono.replace(args[0], args[1], int(args[2]))
                elif len(args) == 2:
                    cap_mono = cap_mono.replace(args[0], args[1])
                elif len(args) == 1:
                    cap_mono = cap_mono.replace(args[0], '')
        cap_mono = cap_mono.replace('%%', '|').replace('&%&', '{').replace('$%$', '}')
    return file_, cap_mono


async def get_ss(up_path, ss_no):
    thumbs_path, tstamps = await take_ss(up_path, total=min(ss_no, 250), gen_ss=True)
    th_html = f"📌 <h4>{ospath.basename(up_path)}</h4><br>📇 <b>Total Screenshots:</b> {ss_no}<br><br>"
    up_sem = Semaphore(25)
    async def telefile(thumb):
        async with up_sem:
            tele_id = await sync_to_async(upload_file, ospath.join(thumbs_path, thumb))
            return tele_id[0], tstamps[thumb]
    tasks = [telefile(thumb) for thumb in natsorted(await listdir(thumbs_path))]
    results = await gather(*tasks)
    th_html += ''.join(f'<img src="https://graph.org{tele_id}"><br><pre>Screenshot at {stamp}</pre>' for tele_id, stamp in results)
    await aiormtree(thumbs_path)
    link_id = (await telegraph.create_page(title="ScreenShots X", content=th_html))["path"]
    return f"https://graph.org/{link_id}"


async def get_mediainfo_link(up_path):
    stdout, __, _ = await cmd_exec(ssplit(f'mediainfo "{up_path}"'))
    tc = f"📌 <h4>{ospath.basename(up_path)}</h4><br><br>"
    if len(stdout) != 0:
        tc += parseinfo(stdout)
    link_id = (await telegraph.create_page(title="MediaInfo X", content=tc))["path"]
    return f"https://graph.org/{link_id}"


def get_md5_hash(up_path):
    md5_hash = md5()
    with open(up_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            md5_hash.update(byte_block)
        return md5_hash.hexdigest()
