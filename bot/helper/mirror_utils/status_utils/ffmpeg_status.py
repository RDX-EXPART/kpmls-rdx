from time import time

from bot import LOGGER
from bot.helper.utils import (
    get_readable_file_size,
    get_readable_time,
)
from bot.helper.ext_utils.bot_utils import MirrorStatus


class FfmpegStatus:
    def __init__(self, listener, obj, gid, status=""):
        self._obj = obj
        self._cstatus = status
        self.engine = 'FFMPEG'
        self.__name = listener.name
        self.__size = listener.size
        self.__gid = gid
        self.__listener = listener
        self.upload_details = listener.upload_details
        self.__uid = listener.uid
        self.__start_time = time()
        self.message = listener.message
        
        

    def speed(self):
        return f"{get_readable_file_size(self._obj.speed_raw)}/s"

    def processed_bytes(self):
        return get_readable_file_size(self._obj.processed_bytes)

    def progress(self):
        return f"{round(self._obj.progress_raw, 2)}%"

    def gid(self):
        return self.__gid

    def name(self):
        return self.__listener.name

    def size(self):
        return get_readable_file_size(self.__listener.size)

    def eta(self):
        return get_readable_time(self._obj.eta_raw) if self._obj.eta_raw else 0

    def status(self):
        return self._cstatus 
        
    def task(self):
        return self

    async def cancel_task(self):
        LOGGER.info(f"Cancelling {self._cstatus}: {self.__listener.name}")
        self.__listener.is_cancelled = True
        if self.__listener._subprocess and self.__listener._subprocess.returncode is None:
            try:
                self.__listener._subprocess.kill()
            except Exception:
                pass
        await self.__listener.on_upload_error(f"{self._cstatus} stopped by user!")

