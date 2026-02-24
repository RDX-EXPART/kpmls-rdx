from hashlib import md5
from time import strftime, gmtime, time
from re import IGNORECASE, sub as re_sub, search as re_search
from shlex import split as ssplit
from natsort import natsorted
from os import path as ospath
from aiofiles.os import remove as aioremove, path as aiopath, mkdir, makedirs, listdir
from aioshutil import rmtree as aiormtree
from contextlib import suppress
from asyncio import create_subprocess_exec, gather, Semaphore
from asyncio.subprocess import PIPE
from telegraph import upload_file
from langcodes import Language

from bot import bot_cache, LOGGER, MAX_SPLIT_SIZE, config_dict, user_data
from bot.modules.mediainfo import parseinfo
from bot.helper.ext_utils.bot_utils import cmd_exec, sync_to_async, get_readable_file_size, get_readable_time
from bot.helper.ext_utils.fs_utils import ARCH_EXT, get_mime_type
from bot.helper.ext_utils.telegraph_helper import telegraph

# Smart rename import
from bot.helper.ext_utils.smart_rename import smart_rename_movie


async def format_filename(file_, user_id, dirpath=None, isMirror=False):
    user_dict = user_data.get(user_id, {})
    ftag, ctag = ('m', 'MIRROR') if isMirror else ('l', 'LEECH')
    prefix = config_dict[f'{ctag}_FILENAME_PREFIX'] if (val:=user_dict.get(f'{ftag}prefix', '')) == '' else val
    remname = config_dict[f'{ctag}_FILENAME_REMNAME'] if (val:=user_dict.get(f'{ftag}remname', '')) == '' else val
    suffix = config_dict[f'{ctag}_FILENAME_SUFFIX'] if (val:=user_dict.get(f'{ftag}suffix', '')) == '' else val
    lcaption = config_dict['LEECH_FILENAME_CAPTION'] if (val:=user_dict.get('lcaption', '')) == '' else val

    prefile_ = file_

    file_ = re_sub(r'www\S+', '', file_, flags=IGNORECASE)
    file_ = re_sub(r'(^\s*-\s*|(\s*-\s*){2,})', '', file_)

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

    file_ = smart_rename_movie(file_, skip_series=False)
    LOGGER.info(f"Smart Rename : {file_}")

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
        _extOutName = '.'.join(fileDict[:-1]).replace('.', ' ').replace('-', ' ')
        _newExtFileName = f"{_extOutName}{suffix}.{fileDict[-1]}"
        if len(_extOutName) > (64 - (sufLen + _extIn)):
            _newExtFileName = (_extOutName[: 64 - (sufLen + _extIn)] + f"{suffix}.{fileDict[-1]}")
        file_ = _newExtFileName
    elif suffix:
        suffix = suffix.replace('\s', ' ')
        file_ = f"{ospath.splitext(file_)[0]}{suffix}{ospath.splitext(file_)[1]}" if '.' in file_ else f"{file_}{suffix}"

    cap_mono = f"<{config_dict['CAP_FONT']}>{nfile_}</{config_dict['CAP_FONT']}>" if config_dict['CAP_FONT'] else nfile_
    return file_, cap_mono
