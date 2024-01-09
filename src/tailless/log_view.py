from itertools import islice
import mmap
import os
import re
from typing import NamedTuple, IO, TypeAlias

from rich.text import Text
from rich.highlighter import ReprHighlighter

from textual import on
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.geometry import Size
from textual.scroll_view import ScrollView
from textual.cache import LRUCache
from textual.strip import Strip
from textual.widget import Widget
from textual.widgets import Label
from textual.reactive import reactive

from .filter_dialog import FilterDialog


OffsetPair: TypeAlias = tuple[int, int]


class LineKey:
    dimmed: bool
    highlighted: bool


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
        self._text_cache: LRUCache[int, Text] = LRUCache(1000)

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

    def get_text(self, line_index: int) -> Text:
        try:
            text = self._text_cache[line_index]
        except KeyError:
            line = self.get_line(line_index).rstrip("\n")
            text = Text(line)
            text.expand_tabs(4)
            ReprHighlighter().highlight(text)
            self._text_cache[line_index] = text
        return text.copy()

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


class LogLines(ScrollView):
    DEFAULT_CSS = """
    LogLines {
        border: heavy transparent;
        .loglines--filter-highlight {
            background: $secondary;
            color: auto;
        }
        &:focus {
            border: heavy $accent;
        }
    }
    """
    COMPONENT_CLASSES = {"loglines--filter-highlight"}

    show_find = reactive(False)
    find = reactive("")
    case_sensitive = reactive(False)
    regex = reactive(False)

    def __init__(self, file_path: str) -> None:
        super().__init__()
        self.mapped_file = MappedFile(file_path)
        self._render_line_cache: LRUCache[int, Strip] = LRUCache(maxsize=1000)
        self._max_width = 0

    def clear_caches(self) -> None:
        self._render_line_cache.clear()

    def notify_style_update(self) -> None:
        self.clear_caches()

    def on_mount(self) -> None:
        self.mapped_file.open()
        self.mapped_file.scan_block(0, self.mapped_file.size)

    def on_unmount(self) -> None:
        self.mapped_file.close()

    def render_line(self, y: int) -> Strip:
        scroll_x, scroll_y = self.scroll_offset
        index = y + scroll_y
        style = self.rich_style
        width, height = self.size
        if index >= self.mapped_file.line_count:
            return Strip.blank(width, style)
        try:
            strip = self._render_line_cache[index]
        except KeyError:
            text = self.mapped_file.get_text(index)
            text.stylize_before(style)

            if self.find and self.show_find:
                self.highlight_find(text)
            strip = Strip(text.render(self.app.console), text.cell_len)
            self._render_line_cache[index] = strip
            self._max_width = max(self._max_width, strip.cell_length)

        strip = strip.crop_extend(scroll_x, scroll_x + width, style)

        return strip

    def highlight_find(self, text: Text) -> None:
        filter_style = self.get_component_rich_style("loglines--filter-highlight")
        if self.regex:
            try:
                re.compile(self.find)
            except Exception:
                return
            matches = list(
                re.finditer(
                    self.find,
                    text.plain,
                    flags=0 if self.case_sensitive else re.IGNORECASE,
                )
            )
            if matches:
                for match in matches:
                    text.stylize(filter_style, *match.span())
            else:
                text.stylize("dim")
        else:
            if not text.highlight_words(
                [self.find], filter_style, case_sensitive=self.case_sensitive
            ):
                text.stylize("dim")

    def on_idle(self) -> None:
        self.virtual_size = Size(self._max_width, self.mapped_file.line_count)

    def watch_show_find(self) -> None:
        self.clear_caches()

    def watch_find(self) -> None:
        self.clear_caches()

    def watch_case_sensitive(self) -> None:
        self.clear_caches()

    def watch_regex(self) -> None:
        self.clear_caches()


class LogView(Vertical):
    DEFAULT_CSS = """
    LogView {
        layers: dialogs;
        .float {
            layer: dialog;
            offset-x: 120%;
            transition: offset 200ms;
            &.visible {
                offset-x: 0%;
            }
        }
    }
    """

    show_find = reactive(False)

    def __init__(self, file_path: str) -> None:
        self.file_path = file_path
        super().__init__()

    def compose(self) -> ComposeResult:
        yield LogLines(self.file_path)
        yield FilterDialog()

    @on(FilterDialog.Update)
    def filter_dialog_update(self, event: FilterDialog.Update) -> None:
        log_lines = self.query_one(LogLines)
        log_lines.find = event.find
        log_lines.regex = event.regex
        log_lines.case_sensitive = event.case_sensitive

    def watch_show_find(self, show_find: bool) -> None:
        filter_dialog = self.query_one(FilterDialog)
        filter_dialog.set_class(show_find, "visible")
        self.query_one(LogLines).show_find = show_find
        if show_find:
            filter_dialog.query_one("Input").focus()
        else:
            self.query_one(LogLines).focus()

    @on(FilterDialog.Dismiss)
    def dismiss_filter_dialog(self, event: FilterDialog.Dismiss) -> None:
        event.stop()
        self.show_find = False


if __name__ == "__main__":
    import sys

    mapped_file = MappedFile(sys.argv[1])

    mapped_file.open()
    mapped_file.scan_block(0, mapped_file.size)

    for n in range(10):
        print(repr(mapped_file.get_line(n)))

    mapped_file.close()
