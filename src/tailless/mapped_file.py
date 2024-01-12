from datetime import datetime
from itertools import islice
import mmap
import os
from typing import TypeAlias

from rich.text import Text

from textual.cache import LRUCache


from .highlighter import LogHighlighter
from .timestamps import parse_extract

OffsetPair: TypeAlias = tuple[int, int]


class MappedFile:
    def __init__(self, path: str) -> None:
        self.path = path
        self.fileno: int | None = None
        self._mmap: mmap.mmap | None = None
        self.size = 0
        self._lines: list[OffsetPair] = []
        self._line_breaks: list[int] = []
        self._line_offsets: list[OffsetPair] = []
        self._line_cache: LRUCache[int, str] = LRUCache(1000)
        self._text_cache: LRUCache[int, tuple[Text, datetime | None]] = LRUCache(1000)
        self.highlighter = LogHighlighter()

    @property
    def line_count(self) -> int:
        return len(self._line_offsets)

    def is_open(self) -> bool:
        return self.fileno is not None

    def open(self) -> bool:
        try:
            self.fileno = os.open(self.path, os.O_RDWR)
        except IOError:
            return False
        self._mmap = mmap.mmap(self.fileno, 0, flags=mmap.PROT_READ)
        self.size = len(self._mmap)
        return True

    def close(self) -> None:
        self._mmap = None
        if self.fileno is not None:
            os.close(self.fileno)
            self.fileno = None

    def get_raw(self, start: int, end: int) -> bytes:
        return self._mmap[start:end]

    def get_line(self, line_index: int) -> str:
        try:
            line = self._line_cache[line_index]
        except KeyError:
            start, end = self._line_offsets[line_index]
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

        offsets = [
            pair for pair in zip(self._line_breaks, islice(self._line_breaks, 1, None))
        ]
        self._line_offsets[:] = offsets
