from datetime import datetime
import mmap
import os


from rich.text import Text
from textual.cache import LRUCache


from .highlighter import LogHighlighter
from .timestamps import parse_extract
from .watcher import Watcher, WatchedFile


class MappedFile:
    def __init__(self, watcher: Watcher, path: str) -> None:
        self.watcher = watcher
        self.path = path
        self.fileno: int | None = None
        self._mmap: mmap.mmap | None = None
        self.size = 0
        self._line_breaks: list[int] = []
        self._line_cache: LRUCache[int, str] = LRUCache(1000)
        self._text_cache: LRUCache[int, tuple[str, Text, datetime | None]] = LRUCache(
            1000
        )
        self.highlighter = LogHighlighter()

    @property
    def line_count(self) -> int:
        return len(self._line_breaks)

    def is_open(self) -> bool:
        return self.fileno is not None

    def open(self) -> bool:
        try:
            self.fileno = os.open(self.path, os.O_RDWR)
        except IOError:
            raise
            return False
        self.size = self.watcher.add(self.path, self._file_updated, self._file_error)
        self._mmap = mmap.mmap(self.fileno, self.size, flags=mmap.PROT_READ)

        return True

    def _file_updated(self, watched_file: WatchedFile) -> None:
        print(watched_file)

    def _file_error(self, watched_file: WatchedFile, error: Exception) -> None:
        pass

    def close(self) -> None:
        self._mmap = None
        if self.fileno is not None:
            os.close(self.fileno)
            self.fileno = None

    def get_raw(self, start: int, end: int) -> bytes:
        assert self._mmap is not None
        raw_data = self._mmap[start : min(end, self.size - 1)]
        return raw_data

    def get_line(self, line_index: int) -> str:
        try:
            line = self._line_cache[line_index]
        except KeyError:
            start = self._line_breaks[line_index]
            end = (
                self._line_breaks[line_index + 1]
                if line_index + 1 < len(self._line_breaks)
                else self.size
            )
            line_bytes = self.get_raw(start, end)
            line = line_bytes.decode("utf-8", errors="replace")
            self._line_cache[line_index] = line
        return line

    def get_text(self, line_index: int) -> tuple[str, Text, datetime | None]:
        try:
            line, text, timestamp = self._text_cache[line_index]
        except KeyError:
            line = self.get_line(line_index).rstrip("\n")
            _, line, timestamp = parse_extract(line)
            text = Text(line)
            text = self.highlighter(text)
            text.expand_tabs(4)
            self._text_cache[line_index] = (line, text, timestamp)
        return line, text.copy(), timestamp

    def _scan_line_breaks(self, start: int, end: int) -> list[int]:
        assert self._mmap is not None
        chunk = self._mmap[start:end]
        offset = 0
        offsets: list[int] = []
        while offset := chunk.find(b"\n", offset) + 1:
            offsets.append(offset + start)
        return offsets

    def scan_block(self, start: int, end: int):
        self._line_breaks.extend(self._scan_line_breaks(start, end))
        if start == 0:
            self._line_breaks.append(start)
        self._line_breaks.sort()
