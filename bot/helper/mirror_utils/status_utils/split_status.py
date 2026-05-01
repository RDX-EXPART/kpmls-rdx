#!/usr/bin/env python3
from time import time
from os import listdir
from os import path as ospath

from bot import LOGGER
from bot.helper.ext_utils.bot_utils import EngineStatus, get_readable_file_size, get_readable_time, MirrorStatus


class SplitStatus:
    def __init__(self, name, size, gid, listener):
        self.__name = name
        self.__gid = gid
        self.__size = size
        self.__listener = listener
        self.__start_time = time()
        self.upload_details = listener.upload_details
        self.message = listener.message

    def gid(self):
        return self.__gid

    def _generated_size(self):
        dirpath = getattr(self.__listener, '_split_dirpath', None)
        filename = getattr(self.__listener, '_split_filename', self.__name)
        if not dirpath or not ospath.isdir(dirpath):
            return 0
        base, ext = ospath.splitext(filename)
        prefixes = (f"{base}.part", f"{filename}.")
        total = 0
        try:
            for item in listdir(dirpath):
                if item == filename:
                    continue
                if item.startswith(prefixes) or (ext and item.startswith(f"{base}.") and item.endswith(ext)):
                    fpath = ospath.join(dirpath, item)
                    if ospath.isfile(fpath):
                        total += ospath.getsize(fpath)
        except Exception:
            return 0
        return min(total, self.__size)

    def processed_raw(self):
        return self._generated_size()

    def progress_raw(self):
        try:
            return min(100, max(0, self.processed_raw() / self.__size * 100))
        except Exception:
            return 0

    def progress(self):
        return f'{round(self.progress_raw(), 2)}%'

    def speed_raw(self):
        elapsed = max(time() - self.__start_time, 1)
        return self.processed_raw() / elapsed

    def speed(self):
        return f'{get_readable_file_size(self.speed_raw())}/s'

    def name(self):
        return self.__name

    def size(self):
        return get_readable_file_size(self.__size)

    def eta(self):
        speed = self.speed_raw()
        if speed <= 0:
            return '-'
        return get_readable_time((self.__size - self.processed_raw()) / speed)

    def status(self):
        return MirrorStatus.STATUS_SPLITTING

    def processed_bytes(self):
        return get_readable_file_size(self.processed_raw())

    def download(self):
        return self

    async def cancel_download(self):
        LOGGER.info(f'Cancelling Split: {self.__name}')
        proc = getattr(self.__listener, '_subprocess', None)
        if proc and proc != 'cancelled':
            try:
                proc.kill()
            except Exception:
                pass
        self.__listener._subprocess = 'cancelled'
        await self.__listener.onUploadError('splitting stopped by user!')

    def eng(self):
        return EngineStatus().STATUS_SPLIT_MERGE
