from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import mmap
import re
import time
from queue import Empty, Queue
from threading import Thread, Event
from typing import Mapping

import rich.repr
from rich.text import Text
from rich.segment import Segment
from rich.style import Style

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.cache import LRUCache
from textual.containers import Horizontal
from textual import events
from textual.geometry import Size, clamp, Region
from textual.message import Message
from textual.reactive import reactive
from textual.css.query import NoMatches
from textual.scroll_view import ScrollView
from textual import scrollbar
from textual.cache import LRUCache
from textual.widget import Widget
from textual.widgets import Label, Static
from textual import work
from textual.worker import Worker, get_current_worker
from textual.widget import Widget


from textual.strip import Strip


from textual.suggester import Suggester

from .highlighter import LogHighlighter
from .filter_dialog import FilterDialog
from .line_panel import LinePanel
from .log_file import LogFile
from . import log_format
from .watcher import Watcher

SPLIT_REGEX = r"[\s/\[\]]"


MAX_LINE_LENGTH = 1000


@dataclass
class LineRead(Message):
    index: int
    start: int
    end: int
    line: str


class LineReader(Thread):
    def __init__(self, log_lines: LogLines) -> None:
        self.log_lines = log_lines
        self.queue: Queue[tuple[int, int, int]] = Queue(maxsize=1000)
        self.exit_event = Event()
        self.pending: set[tuple[int, int, int]] = set()
        super().__init__()

    def request_line(self, index: int, start: int, end: int) -> None:
        request = (index, start, end)
        if request not in self.pending:
            self.queue.put((index, start, end))

    def stop(self) -> None:
        self.exit_event.set()
        self.queue.put((-1, 0, 0))
        self.join()

    def run(self) -> None:
        log_lines = self.log_lines
        while not self.exit_event.is_set():
            try:
                request = self.queue.get(timeout=0.2)
            except Empty:
                continue
            else:
                self.pending.discard(request)
                index, start, end = request
                self.queue.task_done()
                if self.exit_event.is_set() or index == -1:
                    break
                log_lines.post_message(
                    LineRead(
                        index,
                        start,
                        end,
                        log_lines._get_line(start, end),
                    )
                )


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


class InfoOverlay(Widget):
    DEFAULT_CSS = """
    InfoOverlay {
        display: none;
        dock: bottom;        
        layer: overlay;
        width: 1fr;
        visibility: hidden;        
    }

    InfoOverlay Horizontal {
        width: 1fr;
        align: center bottom;
    }
    
    InfoOverlay Label {
        visibility: visible;
        width: auto;
        height: 1;
        background: $panel;
        color: $success;
        padding: 0 1;

        &:hover {
            background: $success;
            color: auto 90%;
            text-style: bold;
        }
    }
    """

    message = reactive("")

    def compose(self) -> ComposeResult:
        self.tooltip = "Click to tail file"
        with Horizontal():
            yield Label(" +100 lines ")

    def watch_message(self, message: str) -> None:
        self.query_one(Label).update(message)
        self.display = bool(message)

    def on_click(self) -> None:
        self.post_message(TailFile())


@dataclass
class SizeChanged(Message, bubble=False):
    size: int

    def can_replace(self, message: Message) -> bool:
        return isinstance(message, SizeChanged)


@dataclass
class FileError(Message, bubble=False):
    error: Exception


@dataclass
class PendingLines(Message):
    count: int


class DismissOverlay(Message):
    pass


@rich.repr.auto
@dataclass
class NewBreaks(Message):
    breaks: list[int]
    scanned_size: int = 0
    tail: bool = False

    def __rich_repr__(self) -> rich.repr.Result:
        yield "scanned_size", self.scanned_size
        yield "tail", self.tail


@dataclass
class TailFile(Message):
    tail: bool = True


class ScanProgressBar(Static):
    SCOPED_CSS = False
    DEFAULT_CSS = """
    ScanProgressBar {
        width: 100%;
        margin: 2 4;
        dock: top;                    
        padding: 1 2;
        background: $primary;        
        display: block;
        text-align: center;
        display: none;
     
    }

    LogLines:focus ScanProgressBar.-has-content {
        display: block;
    }
    """

    message = reactive[str]

    def update_progress(self, progress: int, total: int, line_count: int) -> None:
        percentage = int((progress / total) * 100.0)
        line_count_thousands = line_count // 1000
        self.update(
            f"Scanning [b]{percentage}%[/] ({line_count_thousands:,}K lines)- ESCAPE to cancel"
        )
        self.add_class("-has-content")


@dataclass
class ScanProgress(Message):
    total: int
    progress: int
    scan_start: int


@dataclass
class ScanComplete(Message):
    size: int
    scan_start: int


class LogFooter(Widget):
    DEFAULT_CSS = """
    LogFooter {
        layout: horizontal;
        height: 1;
        width: 1fr;
        dock: bottom;
        Horizontal {
            width: 1fr;
            height: 1;
            
        }
        .tail {
            # background: $error 10%;
            color: $warning;
            padding: 0 1;
            
            &.on {
            
                #  background: $success 10%;
                #  color: $success;               
             }
            
        }
        .line-no {
            width: auto;
            height: 1;
            color: $warning;
            padding: 0 1 0 0;
        }
        .timestamp {
            width: auto;
            height: 1;
            color: $warning;
            padding: 0 1;
        }
    }
    """
    line_no: reactive[int | None] = reactive(None)
    timestamp: reactive[datetime | None] = reactive(None)
    tail: reactive[bool] = reactive(False)

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Label(" [b]✔[/] [bold reverse]T[/]ail ", classes="tail key")
        yield Label("", classes="timestamp")
        yield Label("", classes="line-no")

    def watch_tail(self, tail: bool) -> None:
        try:
            tail_label = self.query_one(".tail", Label)
        except NoMatches:
            return
        tail_label.update(
            "[bold reverse] ✔ Tail " if tail else " [dim]✔[/] [bold reverse]T[/]ail "
        )
        tail_label.set_class(tail, "on")

    def watch_line_no(self, line_no: int | None) -> None:
        self.query_one(".line-no", Label).update(
            "" if line_no is None else f"• Line {line_no+1:,}"
        )

    def watch_timestamp(self, timestamp: datetime | None) -> None:
        if timestamp is None:
            self.query_one(".timestamp", Label).update("")
        else:
            self.query_one(".timestamp", Label).update(f"{timestamp:%x %X}")


class LogLines(ScrollView, inherit_bindings=False):
    BINDINGS = [
        Binding("up", "scroll_up", "Scroll Up", show=False),
        Binding("down", "scroll_down", "Scroll Down", show=False),
        Binding("left", "scroll_left", "Scroll Up", show=False),
        Binding("right", "scroll_right", "Scroll Right", show=False),
        Binding("home", "scroll_home", "Scroll Home", show=False),
        Binding("end", "scroll_end", "Scroll End", show=False),
        Binding("pageup", "page_up", "Page Up", show=False),
        Binding("pagedown", "page_down", "Page Down", show=False),
        Binding("enter", "select", "Select line", show=False),
        Binding("escape", "dismiss", "Dismiss", show=False, priority=True),
    ]

    DEFAULT_CSS = """
    LogLines {
        scrollbar-gutter: stable;
        overflow: scroll;
        border: heavy transparent;        
        .loglines--filter-highlight {
            background: $secondary;
            color: auto;
        }
        .loglines--pointer-highlight {
            background: $primary;
        }
        &:focus {
            border: heavy $accent;
        }
        border-subtitle-color: $success;
        border-subtitle-align: center;        
        align: center middle;

        &.-scanning {
            tint: $background 30%;
        }
        .loglines--line-numbers {
            color: $success 50%;            
        }
        .loglines--line-numbers-active {
            color: $success;            
            text-style: bold;
        }       
    }
    """
    COMPONENT_CLASSES = {
        "loglines--filter-highlight",
        "loglines--pointer-highlight",
        "loglines--line-numbers",
        "loglines--line-numbers-active",
    }

    show_find = reactive(False)
    find = reactive("")
    case_sensitive = reactive(False)
    regex = reactive(False)
    show_gutter = reactive(False)
    pointer_line: reactive[int | None] = reactive(None, repaint=False)
    is_scrolling: reactive[int] = reactive(int)
    pending_lines: reactive[int] = reactive(int)
    tail: reactive[bool] = reactive(True)
    show_line_numbers: reactive[bool] = reactive(False)

    @dataclass
    class PointerMoved(Message):
        pointer_line: int | None

        def can_replace(self, message: Message) -> bool:
            return isinstance(message, LogLines.PointerMoved)

    def __init__(self, watcher: Watcher, file_path: str) -> None:
        super().__init__()
        self.watcher = watcher
        self.file_path = file_path
        self.log_file = LogFile(file_path)
        self._render_line_cache: LRUCache[object, Strip] = LRUCache(maxsize=1000)
        self._max_width = 0
        self._search_index: LRUCache[str, str] = LRUCache(maxsize=10000)
        self._suggester = SearchSuggester(self._search_index)
        self.icons: dict[int, str] = {}
        self._line_breaks: list[int] = []
        self._line_cache: LRUCache[tuple[int, int], str] = LRUCache(10000)
        self._text_cache: LRUCache[
            tuple[int, int, bool], tuple[str, Text, datetime | None]
        ] = LRUCache(1000)
        self.highlighter = LogHighlighter()
        self.initial_scan_worker: Worker | None = None
        self._line_count = 0
        self._scanned_size = 0
        self._scan_start = 0
        self._gutter_width = 0
        self._line_reader = LineReader(self)

    @property
    def line_count(self) -> int:
        return self._line_count

    @property
    def gutter_width(self) -> int:
        return self._gutter_width

    @property
    def focusable(self) -> bool:
        """Can this widget currently be focused?"""
        return self.can_focus and self.visible and not self._self_or_ancestors_disabled

    def compose(self) -> ComposeResult:
        yield ScanProgressBar()

    def clear_caches(self) -> None:
        # self._render_line_cache.clear()
        self._line_cache.clear()
        self._text_cache.clear()

    def notify_style_update(self) -> None:
        self.clear_caches()

    def validate_pointer_line(self, pointer_line: int | None) -> int | None:
        if pointer_line is None:
            return None
        if pointer_line < 0:
            return 0
        if pointer_line >= self.line_count:
            return self.line_count - 1
        return pointer_line

    def on_mount(self) -> None:
        self.loading = True
        self.add_class("-scanning")

        # fileno, size = self.watcher.add(self.file_path, size_changed, watch_error)
        # self.log_file.open()
        # size = self.log_file.size

        self._line_reader.start()

        # self.disabled = True
        # self._scan_start = max(0, size - 1)
        self.initial_scan_worker = self.run_scan()
        # self.start_tail()

    def start_tail(self) -> None:
        def size_changed(size: int, breaks: list[int]) -> None:
            """Callback when the file changes size."""
            # time.sleep(0)
            if self.message_queue_size > 10:
                while self.message_queue_size > 2:
                    time.sleep(0.1)
            self.post_message(NewBreaks(breaks, size, tail=True))

        def watch_error(error: Exception) -> None:
            """Callback when there is an error watching the file."""
            self.post_message(FileError(error))

        self.watcher.add(
            self.log_file,
            size_changed,
            watch_error,
        )

    @work(thread=True)
    def run_scan(self) -> None:
        worker = get_current_worker()

        try:
            if not self.log_file.open(worker.cancelled_event):
                self.loading = False
                return
        except FileNotFoundError:
            self.notify(
                f"File {self.log_file.path.name!r} not found.", severity="error"
            )
            self.loading = False
            return
        except Exception as error:
            self.notify(
                f"Failed to open {self.log_file.path.name!r}; {error}", severity="error"
            )
            self.loading = False
            return

        size = self.log_file.size

        if not size:
            self.post_message(ScanComplete(0, 0))
            return

        log_mmap = mmap.mmap(self.log_file.fileno, size, prot=mmap.PROT_READ)

        breaks: list[int] = []

        scanned_position = position = size
        append = breaks.append
        get_length = breaks.__len__
        rfind = log_mmap.rfind

        monotonic = time.monotonic
        break_time = monotonic()

        while (position := rfind(b"\n", 0, position)) != -1:
            append(position)
            if get_length() % 1000 == 0 and monotonic() - break_time > 0.25:
                break_time = time.monotonic()
                if worker.is_cancelled:
                    break
                self.post_message(ScanProgress(size, size - position, position))
                self.post_message(NewBreaks(breaks.copy()))
                scanned_position = position
                breaks.clear()
        else:
            self.post_message(ScanProgress(size, size, 0))
            if breaks:
                self.post_message(NewBreaks(breaks.copy()))
            self.post_message(ScanComplete(size, 0))
            return

        self.post_message(ScanComplete(size, scanned_position))

    def index_to_span(self, index: int) -> tuple[int, int]:
        if not self._line_breaks:
            return (self._scan_start, self._scan_start)
        index = clamp(index, 0, len(self._line_breaks))
        if index == 0:
            return (self._scan_start, self._line_breaks[0])
        start = self._line_breaks[index - 1]
        end = (
            self._line_breaks[index]
            if index < len(self._line_breaks)
            else max(0, self._scanned_size - 1)
        )
        return (start, end)

    def get_line_from_index_blocking(self, index: int) -> str:
        start, end = self.index_to_span(index)
        return self._get_line(start, end)

    def get_line_from_index(self, index: int) -> str | None:
        start, end = self.index_to_span(index)
        return self.get_line(index, start, end)

    def _get_line(self, start: int, end: int) -> str:
        line_bytes = self.log_file.get_raw(start, end)
        line = line_bytes.decode("utf-8", errors="replace").strip("\n\r").expandtabs(4)
        return line

    def get_line(self, index: int, start: int, end: int) -> str | None:
        cache_key = (start, end)
        try:
            line = self._line_cache[cache_key]
        except KeyError:
            self._line_reader.request_line(index, start, end)
            return None
        return line

    def get_line_blocking(self, index: int, start: int, end: int) -> str:
        cache_key = (start, end)
        try:
            line = self._line_cache[cache_key]
        except KeyError:
            line = self._get_line(start, end)
            self._line_cache[(start, end)] = line
        return line

    def get_text(
        self, line_index: int, abbreviate: bool = False, block: bool = False
    ) -> tuple[str, Text, datetime | None]:
        start, end = self.index_to_span(line_index)
        cache_key = (start, end, abbreviate)
        try:
            line, text, timestamp = self._text_cache[cache_key]
        except KeyError:
            new_line: str | None
            if block:
                new_line = self.get_line_blocking(line_index, start, end)
            else:
                new_line = self.get_line(line_index, start, end)
            if new_line is None:
                return "", Text(""), None
            line = new_line
            if abbreviate and len(line) > MAX_LINE_LENGTH:
                line = line[:MAX_LINE_LENGTH] + "…"

            timestamp, line, text = log_format.parse(line)
            # text = Text(line)
            # text = self.highlighter(text)
            self._text_cache[cache_key] = (line, text, timestamp)
        return line, text.copy(), timestamp

    def on_unmount(self) -> None:
        self._line_reader.stop()
        self.log_file.close()

    def on_idle(self) -> None:
        self.update_line_count()

    def render_lines(self, crop: Region) -> list[Strip]:
        page_height = self.scrollable_content_region.height
        scroll_y = self.scroll_offset.y
        line_count = self.line_count
        index_to_span = self.index_to_span
        for index in range(
            max(0, scroll_y - page_height),
            min(line_count, scroll_y + page_height + page_height),
        ):
            span = index_to_span(index)
            if span not in self._line_cache:
                self._line_reader.request_line(index, *span)
        if self.show_line_numbers:
            max_line_no = self.scroll_offset.y + page_height
            self._gutter_width = len(f"{max_line_no+1} ")
        else:
            self._gutter_width = 0
        if self.pointer_line is not None:
            self._gutter_width += 3
        return super().render_lines(crop)

    def render_line(self, y: int) -> Strip:
        scroll_x, scroll_y = self.scroll_offset
        index = y + scroll_y
        style = self.rich_style
        width, height = self.size
        if index >= self.line_count:
            return Strip.blank(width, style)

        span = self.index_to_span(index)

        is_pointer = self.pointer_line is not None and index == self.pointer_line
        cache_key = (span, is_pointer)

        try:
            strip = self._render_line_cache[cache_key]
        except KeyError:
            line, text, timestamp = self.get_text(index, abbreviate=True)
            text.stylize_before(style)

            if is_pointer:
                pointer_style = self.get_component_rich_style(
                    "loglines--pointer-highlight"
                )
                text.stylize(Style(bgcolor=pointer_style.bgcolor, bold=True))

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
            self._render_line_cache[cache_key] = strip

        if is_pointer:
            pointer_style = self.get_component_rich_style("loglines--pointer-highlight")
            strip = strip.crop_extend(scroll_x, scroll_x + width, pointer_style)
        else:
            strip = strip.crop_extend(scroll_x, scroll_x + width, None)

        if self.show_gutter or self.show_line_numbers:
            line_number_style = self.get_component_rich_style(
                "loglines--line-numbers-active"
                if index == self.pointer_line
                else "loglines--line-numbers"
            )
            if self.pointer_line is not None and index == self.pointer_line:
                icon = "👉"
            else:
                icon = self.icons.get(index, " ")

            if self.show_line_numbers:
                segments = [Segment(f"{index+1} ", line_number_style), Segment(icon)]
            else:
                segments = [Segment(icon)]
            icon_strip = Strip(segments)
            icon_strip = icon_strip.adjust_cell_length(self._gutter_width)
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
            (
                self.scroll_offset.y
                if direction == 1
                else self.scroll_offset.y + self.scrollable_content_region.height - 1
            )
            if self.pointer_line is None
            else self.pointer_line + direction
        )
        if direction == 1:
            line_range = range(start_line, self.line_count)
        else:
            line_range = range(start_line, -1, -1)

        scroll_y = self.scroll_offset.y
        max_scroll_y = scroll_y + self.scrollable_content_region.height - 1
        if self.show_find:
            check_match = self.check_match
            for line_no in line_range:
                line = self.get_line_from_index_blocking(line_no)
                if line and check_match(line):
                    self.pointer_line = line_no
                    break
        else:
            self.pointer_line = next(iter(line_range), self.pointer_line)
        if first:
            self.refresh()
        else:
            if self.pointer_line is not None and (
                self.pointer_line < scroll_y or self.pointer_line > max_scroll_y
            ):
                self.scroll_pointer_to_center()

    def scroll_pointer_to_center(self):
        y_offset = self.pointer_line - self.scrollable_content_region.height // 2
        self.scroll_to(
            y=y_offset,
            animate=abs(y_offset - self.scroll_offset.y) > 1,
            duration=0.2,
        )

    def watch_show_find(self, show_find: bool) -> None:
        self.clear_caches()
        if not show_find:
            self.pointer_line = None

    def watch_find(self, find: str) -> None:
        if not find:
            self.pointer_line = None
        self.clear_caches()

    def watch_case_sensitive(self) -> None:
        self.clear_caches()

    def watch_regex(self) -> None:
        self.clear_caches()

    def watch_pointer_line(
        self, old_pointer_line: int | None, pointer_line: int | None
    ) -> None:
        # if old_pointer_line is not None and pointer_line is not None:
        #     self.scroll_pointer_to_center()
        if old_pointer_line is not None:
            self.refresh_line(old_pointer_line)
        if pointer_line is not None:
            self.refresh_line(pointer_line)
        self.show_gutter = pointer_line is not None
        self.post_message(LogLines.PointerMoved(pointer_line))

    def action_scroll_up(self) -> None:
        if self.pointer_line is None:
            super().action_scroll_up()
        else:
            self.advance_search(-1)
        self.post_message(TailFile(False))

    def action_scroll_down(self) -> None:
        if self.pointer_line is None:
            super().action_scroll_down()
        else:
            self.advance_search(+1)

    def action_scroll_home(self) -> None:
        if self.pointer_line is not None:
            self.pointer_line = 0
        self.scroll_to(y=0, duration=0)
        self.post_message(TailFile(False))

    def action_scroll_end(self) -> None:
        if self.pointer_line is not None:
            self.pointer_line = self.line_count
        if self.scroll_offset.y == self.max_scroll_y:
            self.post_message(TailFile(True))
        else:
            self.scroll_to(y=self.max_scroll_y, duration=0)
            self.post_message(TailFile(False))

    def action_page_down(self) -> None:
        if self.pointer_line is None:
            super().action_page_down()
        else:
            self.pointer_line = (
                self.pointer_line + self.scrollable_content_region.height
            )
            self.scroll_pointer_to_center()
        self.post_message(TailFile(False))

    def action_page_up(self) -> None:
        if self.pointer_line is None:
            super().action_page_up()
        else:
            self.pointer_line = (
                self.pointer_line - self.scrollable_content_region.height
            )
            self.scroll_pointer_to_center()
        self.post_message(TailFile(False))

    def on_click(self, event: events.Click) -> None:
        new_pointer_line = event.y + self.scroll_offset.y - self.gutter.top
        if new_pointer_line == self.pointer_line:
            self.post_message(FilterDialog.SelectLine())
        self.pointer_line = new_pointer_line
        self.post_message(TailFile(False))

    def action_select(self):
        if self.pointer_line is None:
            self.pointer_line = self.scroll_offset.y
        else:
            self.post_message(FilterDialog.SelectLine())

    def action_dismiss(self):
        if self.initial_scan_worker is not None and self.initial_scan_worker.is_running:
            self.initial_scan_worker.cancel()
            self.notify(
                "Stopped scanning. Some lines may not be available.", severity="warning"
            )
        else:
            self.post_message(DismissOverlay())

    def watch_tail(self, tail: bool) -> None:
        if tail:
            self.update_line_count()
            self.scroll_to(y=self.max_scroll_y, animate=False)
            self.pointer_line = None

    def update_line_count(self) -> None:
        line_count = len(self._line_breaks)
        # if self._line_breaks and self._line_breaks[-1] != self._scanned_size:
        #     line_count += 1
        line_count = max(1, line_count)
        self._line_count = line_count
        self.virtual_size = Size(
            self._max_width
            + (self.gutter_width if self.show_gutter or self.show_line_numbers else 0),
            self.line_count,
        )

    @on(NewBreaks)
    def on_new_breaks(self, event: NewBreaks) -> None:
        first = not not self._line_breaks
        event.stop()
        self._scanned_size = max(self._scanned_size, event.scanned_size)
        if not self.tail and event.tail:
            self.post_message(PendingLines(len(self._line_breaks) - self.line_count))

        self._line_breaks.extend(event.breaks)
        if not event.tail:
            self._line_breaks.sort()

        distance_from_end = self.virtual_size.height - self.scroll_offset.y

        pointer_distance_from_end = (
            None
            if self.pointer_line is None
            else self.virtual_size.height - self.pointer_line
        )
        self.loading = False

        if not event.tail or self.tail or first:
            self.update_line_count()

        if self.tail:
            # self.scroll_y = self.max_scroll_y
            if self.pointer_line is not None and pointer_distance_from_end is not None:
                self.pointer_line = self.virtual_size.height - pointer_distance_from_end
            self.scroll_to(y=self.max_scroll_y, animate=False, force=True)
        else:
            # self.scroll_y = self.virtual_size.height - distance_from_end
            # self.refresh()
            self.scroll_to(
                y=self.virtual_size.height - distance_from_end,
                animate=False,
                force=True,
            )

    def watch_scroll_y(self, old_value: float, new_value: float) -> None:
        if self.pointer_line is None:
            self.post_message(self.PointerMoved(int(new_value)))
        super().watch_scroll_y(old_value, new_value)

    @on(scrollbar.ScrollTo)
    def on_scroll_to(self, event: scrollbar.ScrollTo) -> None:
        # Stop tail when scrolling in the Y direction only
        if event.y:
            self.post_message(TailFile(False))

    @on(scrollbar.ScrollUp)
    @on(scrollbar.ScrollDown)
    @on(events.MouseScrollDown)
    @on(events.MouseScrollUp)
    def on_scroll(self, event: events.Event) -> None:
        self.post_message(TailFile(False))

    @on(ScanComplete)
    def on_scan_complete(self, event: ScanComplete) -> None:
        self._scanned_size = max(self._scanned_size, event.size)
        self._scan_start = event.scan_start
        self.update_line_count()
        self.refresh()

    @on(ScanProgress)
    def on_scan_progress(self, event: ScanProgress):
        self._scan_start = event.scan_start

    @on(LineRead)
    def on_line_read(self, event: LineRead) -> None:
        event.stop()
        start = event.start
        end = event.end
        self._render_line_cache.discard(((start, end), True))
        self._render_line_cache.discard(((start, end), False))
        self._line_cache[(start, end)] = event.line
        self._text_cache.discard((start, end, False))
        self._text_cache.discard((start, end, True))
        self.refresh_lines(event.index, 1)


class LogView(Horizontal):
    DEFAULT_CSS = """
    LogView {
        &.show-panel {
            LinePanel {
                display: block;
            }
        }
        LogLines {
            width: 1fr;            
        }     
        LinePanel {
            width: 50%;
            display: none;            
        }              
    }
    """

    BINDINGS = [
        Binding("t", "toggle('tail')"),
        Binding("f", "toggle('show_find')", "Find"),
        Binding("l", "toggle('show_line_numbers')", "Line numbers"),
    ]

    show_find: reactive[bool] = reactive(False)
    show_panel: reactive[bool] = reactive(False)
    show_line_numbers: reactive[bool] = reactive(False)
    tail: reactive[bool] = reactive(False)

    def __init__(self, file_path: str, watcher: Watcher) -> None:
        self.file_path = file_path
        self.watcher = watcher
        super().__init__()

    def compose(self) -> ComposeResult:
        yield (
            log_lines := LogLines(self.watcher, self.file_path).data_bind(
                LogView.tail,
                LogView.show_line_numbers,
                LogView.show_find,
            )
        )
        yield LinePanel()
        yield FilterDialog(log_lines._suggester)
        yield InfoOverlay()
        yield LogFooter().data_bind(LogView.tail)

    @on(FilterDialog.Update)
    def filter_dialog_update(self, event: FilterDialog.Update) -> None:
        log_lines = self.query_one(LogLines)
        log_lines.find = event.find
        log_lines.regex = event.regex
        log_lines.case_sensitive = event.case_sensitive

    def watch_show_find(self, show_find: bool) -> None:
        if not self.is_mounted:
            return
        filter_dialog = self.query_one(FilterDialog)
        filter_dialog.set_class(show_find, "visible")
        if show_find:
            filter_dialog.query_one("Input").focus()
        else:
            self.query_one(LogLines).focus()

    async def watch_show_panel(self, show_panel: bool) -> None:
        self.set_class(show_panel, "show-panel")
        await self.update_panel()

    @on(FilterDialog.Dismiss)
    def dismiss_filter_dialog(self, event: FilterDialog.Dismiss) -> None:
        event.stop()
        self.show_find = False

    @on(FilterDialog.MovePointer)
    def move_pointer(self, event: FilterDialog.MovePointer) -> None:
        event.stop()
        log_lines = self.query_one(LogLines)
        log_lines.advance_search(event.direction)

    @on(FilterDialog.SelectLine)
    def select_line(self) -> None:
        self.show_panel = not self.show_panel

    @on(DismissOverlay)
    def dismiss_overlay(self) -> None:
        if self.show_panel:
            self.show_panel = False
        else:
            self.query_one(LogLines).pointer_line = None

    @on(TailFile)
    def on_tail_file(self, event: TailFile) -> None:
        self.tail = event.tail
        event.stop()
        if not event.tail:
            self.query_one(InfoOverlay).message = ""

    async def update_panel(self) -> None:
        if not self.show_panel:
            return
        pointer_line = self.query_one(LogLines).pointer_line
        if pointer_line is not None:
            line, text, timestamp = self.query_one(LogLines).get_text(
                pointer_line, block=True
            )
            await self.query_one(LinePanel).update(line, text, timestamp)

    @on(LogLines.PointerMoved)
    async def pointer_moved(self, event: LogLines.PointerMoved):
        if event.pointer_line is None:
            self.show_panel = False
        if self.show_panel:
            await self.update_panel()

        self.query_one(LogFooter).line_no = event.pointer_line
        log_lines = self.query_one(LogLines)
        if event.pointer_line is None:
            self.query_one(LogFooter).timestamp = None
        else:
            _, _, timestamp = log_lines.get_text(event.pointer_line, block=True)
            self.query_one(LogFooter).timestamp = timestamp

    @on(PendingLines)
    def on_pending_lines(self, event: PendingLines) -> None:
        event.stop()
        self.query_one(InfoOverlay).message = f"+{event.count:,} lines"

    @on(ScanProgress)
    def on_scan_progress(self, event: ScanProgress):
        event.stop()
        self.query_one(ScanProgressBar).update_progress(
            event.progress, event.total, self.query_one(LogLines).line_count
        )

    @on(ScanComplete)
    def on_scan_complete(self, event: ScanComplete) -> None:
        self.query_one(ScanProgressBar).remove()
        log_lines = self.query_one(LogLines)
        log_lines.loading = False
        self.query_one("LogLines").remove_class("-scanning")
        # log_lines.start_tail()
