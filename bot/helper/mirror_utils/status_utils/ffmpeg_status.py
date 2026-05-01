from time import time

from bot import LOGGER
from bot.helper.utils import (
    get_readable_file_size,
    get_readable_time,
)
from bot.helper.ext_utils.bot_utils import MirrorStatus, EngineStatus


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
    
    def speed_raw(self):
        return self._obj.speed_raw / (time() - self.__start_time)

    def processed_bytes(self):
        return get_readable_file_size(self._obj.processed_bytes)
    
    def processed_raw(self):
        return self._obj.processed_bytes
        
    def progress(self):
        try:
            return f"{round(min(100, max(0, self._obj.progress_raw)), 2)}%"
        except Exception:
            return '0%'

    def gid(self):
        return self.__gid

    def name(self):
        name = getattr(self.__listener, 'name', '') or self.__name
        if not name:
            try:
                name = getattr(self._obj, 'name', '')
            except Exception:
                name = ''
        return name or 'Processing'

    def size(self):
        size = getattr(self.__listener, 'size', 0) or self.__size
        return get_readable_file_size(size)

    def eta(self):
        return get_readable_time(self._obj.eta_raw) if self._obj.eta_raw else 0

    def status(self):
        return self._cstatus 
        
    def task(self):
        return self

    def download(self):
        return self

    async def cancel_download(self):
        LOGGER.info(f'Cancelling Extract: {self.__name}')
        if self.__listener._subprocess is not None:
            self.__listener._subprocess.kill()
        else:
            self.__listener._subprocess = 'cancelled'
        await self.__listener.onUploadError('Ffmpeg stopped by user!')

    def eng(self):
        return EngineStatus().STATUS_SPLIT_MERGE
        
    
