from datetime import datetime
from itertools import islice
import mmap
import os
import re
from typing import Mapping, TypeAlias

from rich.text import Text
from rich.highlighter import ReprHighlighter
from rich.segment import Segment

from textual import on
from textual.app import ComposeResult
from textual.color import Color
from textual.containers import Vertical
from textual.geometry import Size
from textual.reactive import reactive
from textual.scroll_view import ScrollView
from textual.cache import LRUCache

from textual.strip import Strip


from textual.suggester import Suggester

from .filter_dialog import FilterDialog
from .highlighter import LogHighlighter
from .timestamps import parse_extract

OffsetPair: TypeAlias = tuple[int, int]

SPLIT_REGEX = r"[\s/\[\]]"

COLORS = [
    "#881177",
    "#aa3355",
    "#cc6666",
    "#ee9944",
    "#eedd00",
    "#99dd55",
    "#44dd88",
    "#22ccbb",
    "#00bbcc",
    "#0099cc",
    "#3366bb",
    "#663399",
]


class SearchSuggester(Suggester):
    def __init__(self, search_index: Mapping[str, str]) -> None:
        self.search_index = search_index
        super().__init__(use_cache=False, case_sensitive=True)

    async def get_suggestion(self, value: str) -> str | None:
        word = re.split(SPLIT_REGEX, value)[-1]
        start = value[: -len(word)]

        if not word:
            return None
        search_hit = self.search_index.get(word.lower(), None)
        if search_hit is None:
            return None
        return start + search_hit


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

    def get_text(self, line_index: int) -> tuple[Text, datetime | None]:
        try:
            text, timestamp = self._text_cache[line_index]
        except KeyError:
            line = self.get_line(line_index).rstrip("\n")
            _, line, timestamp = parse_extract(line)
            text = Text(line)
            text = self.highlighter(text)
            text.expand_tabs(4)
            self._text_cache[line_index] = (text, timestamp)
        return text.copy(), timestamp

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
    show_gutter = reactive(False)
    pointer_line: reactive[int | None] = reactive(None)
    show_timestamps: reactive[bool] = reactive(True)

    GUTTER_WIDTH = 2

    def __init__(self, file_path: str) -> None:
        super().__init__()
        self.mapped_file = MappedFile(file_path)
        self._render_line_cache: LRUCache[int, Strip] = LRUCache(maxsize=1000)
        self._max_width = 0
        self._search_index: LRUCache[str, str] = LRUCache(maxsize=10000)
        self._suggester = SearchSuggester(self._search_index)
        self.icons: dict[int, str] = {}

    @property
    def line_count(self) -> int:
        return self.mapped_file.line_count

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
            text, timestamp = self.mapped_file.get_text(index)
            if timestamp is not None and self.show_timestamps:
                text = Text.assemble((f"{timestamp} ", "bold  magenta"), text)
            text.stylize_before(style)

            search_index = self._search_index

            for word in re.split(SPLIT_REGEX, text.plain):
                if len(word) <= 1:
                    continue
                for offset in range(1, len(word) - 1):
                    sub_word = word[:offset]
                    if sub_word in search_index:
                        if len(search_index[sub_word]) < len(word):
                            search_index[sub_word.lower()] = word
                    else:
                        search_index[sub_word.lower()] = word

            if self.find and self.show_find:
                self.highlight_find(text)
            strip = Strip(text.render(self.app.console), text.cell_len)
            self._max_width = max(self._max_width, strip.cell_length)
            self._render_line_cache[index] = strip

        strip = strip.crop_extend(scroll_x, scroll_x + width, style)

        if self.show_gutter:
            if self.pointer_line is not None and index == self.pointer_line:
                icon = "👉"
            else:
                icon = self.icons.get(index, " ")
            icon_strip = Strip([Segment(icon)])
            icon_strip = icon_strip.adjust_cell_length(3)
            strip = Strip.join([icon_strip, strip])

        return strip

    def highlight_find(self, text: Text) -> None:
        filter_style = self.get_component_rich_style("loglines--filter-highlight")
        if self.regex:
            try:
                re.compile(self.find)
            except Exception:
                # Invalid regex
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

    def check_match(self, line: str) -> bool:
        if not line:
            return True
        if self.regex:
            return (
                re.match(
                    self.find, line, flags=0 if self.case_sensitive else re.IGNORECASE
                )
                is not None
            )
        else:
            if self.case_sensitive:
                return self.find in line
            else:
                return self.find.lower() in line.lower()

    def advance_search(self, direction: int = 1) -> None:
        first = self.pointer_line is None
        start_line = (
            (self.scroll_offset.y if direction == 1 else self.max_scroll_y)
            if self.pointer_line is None
            else self.pointer_line + direction
        )
        if direction == 1:
            line_range = range(start_line, self.line_count)
        else:
            line_range = range(start_line, -1, -1)

        check_match = self.check_match
        scroll_y = self.scroll_offset.y
        max_scroll_y = scroll_y + self.scrollable_content_region.height - 1
        for line_no in line_range:
            line = self.mapped_file.get_line(line_no)
            if check_match(line):
                self.pointer_line = line_no
                y_offset = (
                    self.pointer_line - self.scrollable_content_region.height // 2
                )
                if self.pointer_line < scroll_y or self.pointer_line > max_scroll_y:
                    self.scroll_to(
                        y=y_offset,
                        animate=abs(y_offset - self.scroll_offset.y) > 1,
                        duration=0.2,
                    )
                self.refresh()
                break

    def on_idle(self) -> None:
        self.virtual_size = Size(
            self._max_width + (self.GUTTER_WIDTH if self.show_gutter else 0),
            self.mapped_file.line_count,
        )
        if self.pointer_line is not None:
            scroll_y = self.scroll_offset.y
            if self.pointer_line < scroll_y:
                self.pointer_line = scroll_y
            elif self.pointer_line >= scroll_y + self.scrollable_content_region.height:
                self.pointer_line = scroll_y + self.scrollable_content_region.height - 1

    def watch_show_find(self, show_find: bool) -> None:
        self.clear_caches()
        if not show_find:
            self.pointer_line = None
            self.show_gutter = False

    def watch_find(self, find: str) -> None:
        if not find:
            self.pointer_line = None
            self.show_gutter = False
        self.clear_caches()

    def watch_case_sensitive(self) -> None:
        self.clear_caches()

    def watch_regex(self) -> None:
        self.clear_caches()

    def watch_show_timestamps(self) -> None:
        self.clear_caches()

    # def watch_scroll_y(self, old_value: float, new_value: float) -> None:
    #     if self.pointer_line is None:
    #         return
    #     scroll_y = self.scroll_offset.y
    #     if self.pointer_line < scroll_y:
    #         self.pointer_line = scroll_y
    #     elif self.pointer_line >= scroll_y + self.container_size.height:
    #         self.pointer_line = scroll_y + self.content_size.height - 1


class LogView(Vertical):
    DEFAULT_CSS = """
    LogView {
                
    }
    """

    show_find = reactive(False)
    show_timestamps = reactive(True)

    def __init__(self, file_path: str) -> None:
        self.file_path = file_path
        super().__init__()

    def compose(self) -> ComposeResult:
        yield (log_lines := LogLines(self.file_path))
        yield FilterDialog(log_lines._suggester)

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

    def watch_show_timestamps(self, show_timestamps: bool) -> None:
        self.query_one(LogLines).show_timestamps = show_timestamps

    @on(FilterDialog.Dismiss)
    def dismiss_filter_dialog(self, event: FilterDialog.Dismiss) -> None:
        event.stop()
        log_lines = self.query_one(LogLines)
        self.show_find = False
        log_lines.show_gutter = False

    @on(FilterDialog.MovePointer)
    def move_pointer(self, event: FilterDialog.MovePointer) -> None:
        event.stop()
        log_lines = self.query_one(LogLines)
        log_lines.show_gutter = True
        log_lines.advance_search(event.direction)


if __name__ == "__main__":
    import sys

    mapped_file = MappedFile(sys.argv[1])

    mapped_file.open()
    mapped_file.scan_block(0, mapped_file.size)

    for n in range(10):
        print(repr(mapped_file.get_line(n)))

    mapped_file.close()
