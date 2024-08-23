from __future__ import annotations

import rich.repr

from abc import ABC, abstractmethod
from dataclasses import dataclass
import platform
from threading import Event, Thread
from typing import Callable, TYPE_CHECKING


def get_watcher() -> WatcherBase:
    """Return an Watcher appropriate for the OS."""

    if platform.system() == "Darwin":
        from toolong.selector_watcher import SelectorWatcher

        return SelectorWatcher()
    else:
        from toolong.poll_watcher import PollWatcher

        return PollWatcher()


if TYPE_CHECKING:
    from .log_file import LogFile


@dataclass
@rich.repr.auto
class WatchedFile:
    """A currently watched file."""

    log_file: LogFile
    callback: Callable[[int, list[int]], None]
    error_callback: Callable[[Exception], None]


class WatcherBase(ABC):
    """Watches files for changes."""

    def __init__(self) -> None:
        self._file_descriptors: dict[int, WatchedFile] = {}
        self._thread: Thread | None = None
        self._exit_event = Event()
        super().__init__()

    @classmethod
    def scan_chunk(cls, chunk: bytes, position: int) -> list[int]:
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

    def close(self) -> None:
        if not self._exit_event.is_set():
            self._exit_event.set()
            self._thread = None

    def start(self) -> None:
        assert self._thread is None
        self._thread = Thread(target=self.run, name=repr(self))
        self._thread.start()

    def add(
        self,
        log_file: LogFile,
        callback: Callable[[int, list[int]], None],
        error_callback: Callable[[Exception], None],
    ) -> None:
        """Add a file to the watcher."""
        fileno = log_file.fileno
        self._file_descriptors[fileno] = WatchedFile(log_file, callback, error_callback)

    @abstractmethod
    def run(self) -> None:
        """Thread runner."""
