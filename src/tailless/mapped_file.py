from datetime import datetime
import mmap
import os
from typing import IO, Iterable

from rich.text import Text
from textual.cache import LRUCache


from .highlighter import LogHighlighter
from .timestamps import parse_extract
from .watcher import Watcher, WatchedFile


class MappedFile:
    def __init__(self, path: str) -> None:
        self.path = path
        self.file: IO[bytes] | None = None
        self.size = 0
        self._line_breaks: list[int] = []
        self._pending_line_breaks: list[int] = []
        self._line_cache: LRUCache[int, str] = LRUCache(1000)
        self._text_cache: LRUCache[int, tuple[str, Text, datetime | None]] = LRUCache(
            1000
        )
        self.highlighter = LogHighlighter()

    @property
    def line_count(self) -> int:
        return len(self._line_breaks)

    def is_open(self) -> bool:
        return self.file is not None

    def open(self, size: int = 0) -> bool:
        try:
            self.file = open(self.path, "rb", buffering=0)
        except IOError:
            raise
            return False

        self.size = size

        return True

    def _file_updated(self, watched_file: WatchedFile) -> None:
        print(watched_file)

    def _file_error(self, watched_file: WatchedFile, error: Exception) -> None:
        pass

    def close(self) -> None:
        if self.file is not None:
            self.file.close()

    def get_raw(self, start: int, end: int) -> bytes:
        assert self.file is not None
        if start >= end:
            return b""
        self.file.seek(start)
        raw_bytes = self.file.read(end - start)
        return raw_bytes

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
            line = self.get_line(line_index).strip("\n")
            _, line, timestamp = parse_extract(line)
            text = Text(line)
            text = self.highlighter(text)
            text.expand_tabs(4)
            self._text_cache[line_index] = (line, text, timestamp)
        return line, text.copy(), timestamp

    def _read_chunks(self, start: int, end: int) -> Iterable[tuple[int, bytes]]:
        _chunk_size = 1024 * 16
        for position in range(start, end, _chunk_size):
            chunk = self.get_raw(position, min(position + _chunk_size, end))
            yield position, chunk

    def _scan_line_breaks(self, start: int, end: int) -> list[int]:
        chunk = self.get_raw(start, end)

        offset = 0
        offsets: list[int] = []
        for chunk_offset, chunk in self._read_chunks(start, end):
            offset = -1
            while (offset := chunk.find(b"\n", offset + 1)) != -1:
                offsets.append(chunk_offset + offset)
            chunk_offset += len(chunk)
        return offsets

    def scan_block(self, start: int, end: int):
        self._line_breaks.extend(self._scan_line_breaks(start, end))
        self._line_breaks.sort()

    def scan_pending_block(self, start: int, end: int) -> None:
        self._pending_line_breaks.extend(self._scan_line_breaks(start, end))


if __name__ == "__main__":
    mapped_file = MappedFile("install.log")
    mapped_file.open()

    print(mapped_file.scan_block(0, 10000))
    print(mapped_file._line_breaks)
