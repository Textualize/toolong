from selectors import DefaultSelector, EVENT_READ
from typing import Callable
import os

from toolong.log_file import LogFile
from toolong.watcher import WatcherBase, WatchedFile


class SelectorWatcher(WatcherBase):
    """Watches files for changes."""

    def __init__(self) -> None:
        self._selector = DefaultSelector()
        super().__init__()

    def close(self) -> None:
        if not self._exit_event.is_set():
            self._exit_event.set()

    def add(
        self,
        log_file: LogFile,
        callback: Callable[[int, list[int]], None],
        error_callback: Callable[[Exception], None],
    ) -> None:
        """Add a file to the watcher."""
        super().add(log_file, callback, error_callback)
        fileno = log_file.fileno
        size = log_file.size
        os.lseek(fileno, size, os.SEEK_SET)
        self._selector.register(fileno, EVENT_READ)

    def run(self) -> None:
        """Thread runner."""

        chunk_size = 64 * 1024
        scan_chunk = self.scan_chunk

        while not self._exit_event.is_set():
            for key, mask in self._selector.select(timeout=0.1):
                if self._exit_event.is_set():
                    break
                if mask & EVENT_READ:
                    fileno = key.fileobj
                    assert isinstance(fileno, int)
                    watched_file = self._file_descriptors.get(fileno, None)
                    if watched_file is None:
                        continue

                    try:
                        position = os.lseek(fileno, 0, os.SEEK_CUR)
                        chunk = os.read(fileno, chunk_size)
                        if chunk:
                            breaks = scan_chunk(chunk, position)
                            watched_file.callback(position + len(chunk), breaks)

                    except Exception as error:
                        watched_file.error_callback(error)
                        self._file_descriptors.pop(fileno, None)
                        self._selector.unregister(fileno)
