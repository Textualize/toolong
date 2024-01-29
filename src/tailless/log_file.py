import os
import mimetypes
from pathlib import Path
from typing import IO
from threading import Event


class LogError(Exception):
    pass


class LogFile:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.file: IO[bytes] | None = None
        self.size = 0
        self.can_tail = False

    def is_open(self) -> bool:
        return self.file is not None

    @property
    def fileno(self) -> int:
        assert self.file is not None
        return self.file.fileno()

    def open(self, exit_event: Event) -> bool:
        ext = self.path.suffix.lower()

        _, encoding = mimetypes.guess_type(self.path.name, strict=False)

        if encoding in ("gzip", "bzip2"):
            return self.open_compressed(exit_event, encoding)

        self.file = open(self.path, "rb", buffering=0)
        self.file.seek(0, os.SEEK_END)
        self.size = self.file.tell()
        self.can_tail = True

        return True

    def open_compressed(self, exit_event: Event, encoding: str) -> bool:
        from tempfile import TemporaryFile

        chunk_size = 1024 * 256

        temp_file = TemporaryFile("wb+")

        compressed_file: IO[bytes]
        if encoding == "gzip":
            import gzip

            compressed_file = gzip.open(self.path, "rb")
        elif encoding == "bzip":
            import bz2

            compressed_file = bz2.open(self.path, "rb")
        else:
            # Shouldn't get here
            raise AssertionError("Not supported")

        try:
            while data := compressed_file.read(chunk_size):
                temp_file.write(data)
                if exit_event.is_set():
                    temp_file.close()
                    return False
        finally:
            compressed_file.close()

        self.file = temp_file
        self.size = temp_file.tell()
        self.can_tail = False
        return True

    def close(self) -> None:
        if self.file is not None:
            self.file.close()
            self.file = None

    def get_raw(self, start: int, end: int) -> bytes:
        if start >= end or self.file is None:
            return b""
        raw_data = os.pread(self.fileno, end - start, start)
        return raw_data

    def read(self, size: int) -> bytes:
        assert self.file is not None, "Must be open to read"
        return self.file.read(size)
