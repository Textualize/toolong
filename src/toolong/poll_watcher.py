from __future__ import annotations

from os import lseek, read, SEEK_CUR
import time


from toolong.watcher import WatcherBase


class PollWatcher(WatcherBase):
    """A watcher that simply polls."""

    def run(self) -> None:
        chunk_size = 64 * 1024
        scan_chunk = self.scan_chunk

        while not self._exit_event.is_set():
            successful_read = False
            for fileno, watched_file in self._file_descriptors.items():
                try:
                    position = lseek(fileno, 0, SEEK_CUR)
                    if chunk := read(fileno, chunk_size):
                        successful_read = True
                        breaks = scan_chunk(chunk, position)
                        watched_file.callback(position + len(chunk), breaks)
                        position += len(chunk)
                except Exception as error:
                    watched_file.error_callback(error)
                    self._file_descriptors.pop(fileno, None)
                    break
            else:
                if not successful_read:
                    time.sleep(0.05)
