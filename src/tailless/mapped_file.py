import os
from typing import IO, Iterable
from threading import Lock


class MappedFile:
    def __init__(self, path: str) -> None:
        self.path = path

        self.file: IO[bytes] | None = None
        self.size = 0
        self._lock = Lock()

    def is_open(self) -> bool:
        return self.fileno is not None

    def open(self) -> int:
        self.file = open(self.path, "rb", buffering=1024 * 64)
        self.file.seek(0, os.SEEK_END)
        self.size = self.file.tell()

        # self.fileno = os.dup(fileno)
        # self.file = os.fdopen(self.fileno, "rb", buffering=1024 * 64)
        # self.size = size

        return self.size

    def close(self) -> None:
        if self.file is not None:
            self.file.close()
            self.file = None
            self.fileno = None

    def get_raw(self, start: int, end: int) -> bytes:
        if start >= end or self.file is None:
            return b""
        with self._lock:
            self.file.seek(start)
            raw_bytes = self.file.read(end - start)
            return raw_bytes

    def _read_chunks(
        self, start: int, end: int, reverse: bool = False
    ) -> Iterable[tuple[int, bytes]]:
        _chunk_size = 1024 * 64

        chunk_range = list(range(start, end, _chunk_size))
        if reverse:
            chunk_range = chunk_range[::-1]
        for position in chunk_range:
            chunk = self.get_raw(position, min(position + _chunk_size, end))
            yield position, chunk

    def scan_line_breaks(
        self, start: int, end: int, reverse: bool = False
    ) -> Iterable[int]:
        chunk = self.get_raw(start, end)

        offset = 0
        offsets: list[int] = []
        for chunk_offset, chunk in self._read_chunks(start, end, reverse=reverse):
            offset = -1
            while (offset := chunk.find(b"\n", offset + 1)) != -1:
                yield chunk_offset + offset
            chunk_offset += len(chunk)
        return offsets
