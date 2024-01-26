from __future__ import annotations

import rich.repr

from dataclasses import dataclass
import os
import time
from selectors import DefaultSelector, EVENT_READ
from threading import Event, Thread, Lock
from typing import Callable, NamedTuple, TYPE_CHECKING


if TYPE_CHECKING:
    from .log_file import LogFile


@dataclass
@rich.repr.auto
class WatchedFile:
    """A currently watched file."""

    log_file: LogFile
    callback: Callable[[int, list[int]], None]
    error_callback: Callable[[Exception], None]

    # def __rich_repr__(self) -> rich.repr.Result:
    #     yield self.path
    #     yield "fileno", self.fileno
    #     yield "size", self.size


def scan_chunk(chunk: bytes, position: int) -> list[int]:
    """Scan line breaks in a binary chunk,

    Args:
        chunk: A binary chunk.
        position: Offset within the file

    Returns:
        A list of indices with new lines.
    """
    breaks: list[int] = []
    offset = 0
    append = breaks.append
    while (offset := chunk.find(b"\n", offset)) != -1:
        append(position + offset)
        offset += 1
    return breaks


class Watcher(Thread):
    """Watches files for changes."""

    def __init__(self) -> None:
        self._selector = DefaultSelector()
        self._file_descriptors: dict[int, WatchedFile] = {}
        self._exit_event = Event()
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
        fileno = log_file.fileno
        size = log_file.size
        self._file_descriptors[fileno] = WatchedFile(log_file, callback, error_callback)
        os.lseek(fileno, size, os.SEEK_SET)
        self._selector.register(fileno, EVENT_READ)

    def run(self) -> None:
        """Thread runner."""

        chunk_size = 64 * 1024

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
                        print(position)
                        chunk = watched_file.log_file.read(chunk_size)
                        print("  ", chunk, position)
                        if chunk:
                            breaks = scan_chunk(chunk, position)
                            print(breaks)
                            watched_file.callback(position + len(chunk), breaks)

                    except Exception as error:
                        watched_file.error_callback(error)
                        self._file_descriptors.pop(fileno, None)
                        self._selector.unregister(fileno)
