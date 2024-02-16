from __future__ import annotations

from datetime import datetime
import os
import mmap
import mimetypes
import time
from pathlib import Path
from typing import IO, Iterable
from threading import Event

import rich.repr

from toolong.format_parser import FormatParser, ParseResult
from toolong.timestamps import TimestampScanner


class LogError(Exception):
    """An error related to logs."""


@rich.repr.auto(angular=True)
class LogFile:
    """A single log file."""

    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.name = self.path.name
        self.file: IO[bytes] | None = None
        self.size = 0
        self.can_tail = False
        self.timestamp_scanner = TimestampScanner()
        self.format_parser = FormatParser()

    def __rich_repr__(self) -> rich.repr.Result:
        yield self.name
        yield "size", self.size

    @property
    def is_open(self) -> bool:
        return self.file is not None

    @property
    def fileno(self) -> int:
        assert self.file is not None
        return self.file.fileno()

    @property
    def is_compressed(self) -> bool:
        _, encoding = mimetypes.guess_type(self.path.name, strict=False)
        return encoding in ("gzip", "bzip2")

    def parse(self, line: str) -> ParseResult:
        """Parse a line."""
        return self.format_parser.parse(line)

    def get_create_time(self) -> datetime | None:
        try:
            stat_result = self.path.stat()
        except Exception:
            return None
        try:
            # This works on Mac
            create_time_seconds = stat_result.st_birthtime
        except AttributeError:
            # No birthtime for Linux, so we assume the epoch start
            return datetime.fromtimestamp(0)
        timestamp = datetime.fromtimestamp(create_time_seconds)
        return timestamp

    def open(self, exit_event: Event) -> bool:

        # Check for compressed files
        _, encoding = mimetypes.guess_type(self.path.name, strict=False)

        # Open compressed files
        if encoding in ("gzip", "bzip2"):
            return self.open_compressed(exit_event, encoding)

        # Open uncompressed file
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
        elif encoding == "bzip2":
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

        temp_file.flush()
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
        return os.pread(self.fileno, end - start, start)

    def get_line(self, start: int, end: int) -> str:

        return (
            self.get_raw(start, end)
            .decode("utf-8", errors="replace")
            .strip("\n\r")
            .expandtabs(4)
        )

    def read(self, size: int) -> bytes:
        assert self.file is not None, "Must be open to read"
        return self.file.read(size)

    def scan_line_breaks(
        self, batch_time: float = 0.25
    ) -> Iterable[tuple[int, list[int]]]:
        """Scan the file for line breaks.

        Args:
            batch_time: Time to group the batches.

        Returns:
            An iterable of tuples, containing the scan position and a list of offsets of new lines.
        """
        fileno = self.fileno
        size = self.size
        if not size:
            return
        log_mmap = mmap.mmap(fileno, size, prot=mmap.PROT_READ)
        rfind = log_mmap.rfind
        position = size
        batch: list[int] = []
        append = batch.append
        get_length = batch.__len__
        monotonic = time.monotonic
        break_time = monotonic()

        while (position := rfind(b"\n", 0, position)) != -1:
            append(position)
            if get_length() % 1000 == 0 and monotonic() - break_time > batch_time:
                break_time = monotonic()
                yield (position, batch)
                batch = []
                append = batch.append
        yield (0, batch)
        log_mmap.close()

    def scan_timestamps(
        self, batch_time: float = 0.25
    ) -> Iterable[list[tuple[int, int, float]]]:
        size = self.size
        if not size:
            return
        log_mmap = mmap.mmap(self.fileno, size, prot=mmap.PROT_READ)

        monotonic = time.monotonic
        scan_time = monotonic()
        scan = self.timestamp_scanner.scan
        line_no = 0
        timestamp = self.get_create_time() or datetime.now()
        position = 0
        results: list[tuple[int, int, float]] = []
        append = results.append
        get_length = results.__len__
        while line_bytes := log_mmap.readline():
            line = line_bytes.decode("utf-8", errors="replace")
            timestamp = scan(line) or timestamp
            append((line_no, position, timestamp.timestamp()))
            position += len(line_bytes)
            line_no += 1
            if (
                results
                and get_length() % 1000 == 0
                and monotonic() - scan_time > batch_time
            ):
                scan_time = monotonic()
                yield results
                results = []
                append = results.append
        if results:
            yield results
