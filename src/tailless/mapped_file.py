from typing import IO, Iterable


from .watcher import WatchedFile


class MappedFile:
    def __init__(self, path: str) -> None:
        self.path = path
        self.file: IO[bytes] | None = None
        self.size = 0

    def is_open(self) -> bool:
        return self.file is not None

    def open(self, size: int = 0) -> bool:
        try:
            self.file = open(self.path, "rb")
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

    def _read_chunks(self, start: int, end: int) -> Iterable[tuple[int, bytes]]:
        _chunk_size = 1024 * 16
        for position in reversed(range(start, end, _chunk_size)):
            chunk = self.get_raw(position, min(position + _chunk_size, end))
            yield position, chunk

    def scan_line_breaks(self, start: int, end: int) -> Iterable[int]:
        chunk = self.get_raw(start, end)

        offset = 0
        offsets: list[int] = []
        for chunk_offset, chunk in self._read_chunks(start, end):
            offset = -1
            while (offset := chunk.find(b"\n", offset + 1)) != -1:
                yield chunk_offset + offset
            chunk_offset += len(chunk)
        return offsets
