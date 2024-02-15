from __future__ import annotations
from dataclasses import dataclass

import rich.repr
from textual.message import Message

from toolong.log_file import LogFile


@dataclass
class Goto(Message):
    pass


@dataclass
class SizeChanged(Message, bubble=False):
    """File size has changed."""

    size: int

    def can_replace(self, message: Message) -> bool:
        return isinstance(message, SizeChanged)


@dataclass
class FileError(Message, bubble=False):
    """An error occurred watching a file."""

    error: Exception


@dataclass
class PendingLines(Message):
    """Pending lines detected."""

    count: int

    def can_replace(self, message: Message) -> bool:
        return isinstance(message, PendingLines)


@rich.repr.auto
@dataclass
class NewBreaks(Message):
    """New line break to add."""

    log_file: LogFile
    breaks: list[int]
    scanned_size: int = 0
    tail: bool = False

    def __rich_repr__(self) -> rich.repr.Result:
        yield "scanned_size", self.scanned_size
        yield "tail", self.tail


class DismissOverlay(Message):
    """Request to dismiss overlay."""


@dataclass
class TailFile(Message):
    """Set file tailing."""

    tail: bool = True


@dataclass
class ScanProgress(Message):
    """Update scan progress bar."""

    message: str
    complete: float
    scan_start: int | None = None


@dataclass
class ScanComplete(Message):
    """Scan has completed."""

    size: int
    scan_start: int


@dataclass
class PointerMoved(Message):
    """Pointer has moved."""

    pointer_line: int | None

    def can_replace(self, message: Message) -> bool:
        return isinstance(message, PointerMoved)
