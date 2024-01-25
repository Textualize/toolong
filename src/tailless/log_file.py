import os
from typing import IO, Iterable
from threading import Lock


class LogFile:
    def __init__(self, path: str) -> None:
        self.path = path

        self.file: IO[bytes] | None = None
        self.size = 0
        self._lock = Lock()

    def is_open(self) -> bool:
        return self.file is not None

    @property
    def fileno(self) -> int:
        assert self.file is not None
        return self.file.fileno()

    def open(self) -> int:
        self.file = open(self.path, "rb", buffering=0)
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

    def get_raw(self, start: int, end: int) -> bytes:
        if start >= end or self.file is None:
            return b""
        return os.pread(self.fileno, end - start, start)
