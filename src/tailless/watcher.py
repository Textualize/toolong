from __future__ import annotations

import rich.repr

from dataclasses import dataclass
import os
import time
from selectors import DefaultSelector, EVENT_READ
from threading import Event, Thread, Lock
from typing import Callable, NamedTuple


@dataclass
@rich.repr.auto
class WatchedFile:
    """A currently watched file."""

    path: str
    fileno: int
    size: int
    callback: Callable[[int], None]
    error_callback: Callable[[Exception], None]

    def __rich_repr__(self) -> rich.repr.Result:
        yield self.path
        yield "fileno", self.fileno
        yield "size", self.size


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
        path: str,
        callback: Callable[[int], None],
        error_callback: Callable[[Exception], None],
    ) -> tuple[int, int]:
        """Add a file to the watcher."""
        fileno = os.open(path, os.O_RDONLY)
        size = os.lseek(fileno, 0, os.SEEK_END)
        self._file_descriptors[fileno] = WatchedFile(
            path, fileno, size, callback, error_callback
        )
        self._selector.register(fileno, EVENT_READ)
        return fileno, size

    def run(self) -> None:
        """Thread runner."""
        return
        while not self._exit_event.is_set():
            for key, mask in self._selector.select(timeout=1):
                if self._exit_event.is_set():
                    break
                if mask & EVENT_READ:
                    fileno = key.fileobj
                    assert isinstance(fileno, int)
                    watched_file = self._file_descriptors.get(fileno, None)
                    if watched_file is None:
                        continue
                    time.sleep(1 / 20)
                    try:
                        size = os.lseek(fileno, 0, os.SEEK_END)
                    except Exception as error:
                        watched_file.error_callback(error)
                        self._file_descriptors.pop(fileno, None)
                        self._selector.unregister(fileno)
                        continue
                    watched_file.size = size
                    try:
                        watched_file.callback(size)
                    except Exception:
                        pass


if __name__ == "__main__":
    import sys

    watcher = Watcher()
    for arg in sys.argv[1:]:
        watcher.add(arg, print)

    watcher.start()
    watcher.join()