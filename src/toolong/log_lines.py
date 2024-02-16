from __future__ import annotations

from dataclasses import dataclass
from queue import Empty, Queue
from operator import itemgetter
import platform
from threading import Event, RLock, Thread

from textual.message import Message
from textual.suggester import Suggester
from toolong.scan_progress_bar import ScanProgressBar
from toolong.find_dialog import FindDialog
from toolong.log_file import LogFile
from toolong.messages import (
    DismissOverlay,
    FileError,
    NewBreaks,
    PendingLines,
    PointerMoved,
    ScanComplete,
    ScanProgress,
    TailFile,
)
from toolong.watcher import WatcherBase


from rich.segment import Segment
from rich.style import Style
from rich.text import Text
from textual import events, on, scrollbar, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.cache import LRUCache
from textual.geometry import Region, Size, clamp
from textual.reactive import reactive
from textual.scroll_view import ScrollView
from textual.strip import Strip
from textual.worker import Worker, get_current_worker


import mmap
import re
import time
from datetime import datetime, timedelta
from typing import Iterable, Literal, Mapping

SPLIT_REGEX = r"[\s/\[\]\(\)\"\/]"


@dataclass
class LineRead(Message):
    """A line has been read from the file."""

    index: int
    log_file: LogFile
    start: int
    end: int
    line: str


class LineReader(Thread):
    """A thread which read lines from log files.

    This allows lines to be loaded lazily, i.e. without blocking.

    """

    def __init__(self, log_lines: LogLines) -> None:
        self.log_lines = log_lines
        self.queue: Queue[tuple[LogFile | None, int, int, int]] = Queue(maxsize=1000)
        self.exit_event = Event()
        self.pending: set[tuple[LogFile | None, int, int, int]] = set()
        super().__init__()

    def request_line(self, log_file: LogFile, index: int, start: int, end: int) -> None:
        request = (log_file, index, start, end)
        if request not in self.pending:
            self.pending.add(request)
            self.queue.put(request)

    def stop(self) -> None:
        """Stop the thread and join."""
        self.exit_event.set()
        self.queue.put((None, -1, 0, 0))
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
                log_file, index, start, end = request
                self.queue.task_done()
                if self.exit_event.is_set() or log_file is None:
                    break
                log_lines.post_message(
                    LineRead(
                        index,
                        log_file,
                        start,
                        end,
                        log_file.get_line(start, end),
                    )
                )


MAX_LINE_LENGTH = 1000


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


class LogLines(ScrollView, inherit_bindings=False):
    BINDINGS = [
        Binding("up,k", "scroll_up", "Scroll Up", show=False),
        Binding("down,j", "scroll_down", "Scroll Down", show=False),
        Binding("left", "scroll_left", "Scroll Up", show=False),
        Binding("right", "scroll_right", "Scroll Right", show=False),
        Binding("home", "scroll_home", "Scroll Home", show=False),
        Binding("end", "scroll_end", "Scroll End", show=False),
        Binding("pageup", "page_up", "Page Up", show=False),
        Binding("pagedown", "page_down", "Page Down", show=False),
        Binding("enter", "select", "Select line", show=False),
        Binding("escape", "dismiss", "Dismiss", show=False, priority=True),
        Binding("m", "navigate(+1, 'm')"),
        Binding("M", "navigate(-1, 'm')"),
        Binding("h", "navigate(+1, 'h')"),
        Binding("H", "navigate(-1, 'h')"),
        Binding("d", "navigate(+1, 'd')"),
        Binding("D", "navigate(-1, 'd')"),
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
            color: $warning 70%;            
        }
        .loglines--line-numbers-active {
            color: $warning;            
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
    can_tail: reactive[bool] = reactive(True)
    show_line_numbers: reactive[bool] = reactive(False)

    def __init__(self, watcher: WatcherBase, file_paths: list[str]) -> None:
        super().__init__()
        self.watcher = watcher
        self.file_paths = file_paths
        self.log_files = [LogFile(path) for path in file_paths]
        self._render_line_cache: LRUCache[
            tuple[LogFile, int, int, bool, str], Strip
        ] = LRUCache(maxsize=1000)
        self._max_width = 0
        self._search_index: LRUCache[str, str] = LRUCache(maxsize=10000)
        self._suggester = SearchSuggester(self._search_index)
        self.icons: dict[int, str] = {}
        self._line_breaks: dict[LogFile, list[int]] = {}
        self._line_cache: LRUCache[tuple[LogFile, int, int], str] = LRUCache(10000)
        self._text_cache: LRUCache[
            tuple[LogFile, int, int, bool], tuple[str, Text, datetime | None]
        ] = LRUCache(1000)
        self.initial_scan_worker: Worker | None = None
        self._line_count = 0
        self._scanned_size = 0
        self._scan_start = 0
        self._gutter_width = 0
        self._line_reader = LineReader(self)
        self._merge_lines: list[tuple[float, int, LogFile]] | None = None
        self._lock = RLock()

    @property
    def log_file(self) -> LogFile:
        return self.log_files[0]

    @property
    def line_count(self) -> int:
        with self._lock:
            if self._merge_lines is not None:
                return len(self._merge_lines)
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
        self._line_reader.start()
        self.initial_scan_worker = self.run_scan(self.app.save_merge)

    def start_tail(self) -> None:
        def size_changed(size: int, breaks: list[int]) -> None:
            """Callback when the file changes size."""
            with self._lock:
                for offset, _ in enumerate(breaks, 1):
                    self.get_line_from_index(self.line_count - offset)
            self.post_message(NewBreaks(self.log_file, breaks, size, tail=True))
            if self.message_queue_size > 10:
                while self.message_queue_size > 2:
                    time.sleep(0.1)

        def watch_error(error: Exception) -> None:
            """Callback when there is an error watching the file."""
            self.post_message(FileError(error))

        self.watcher.add(
            self.log_file,
            size_changed,
            watch_error,
        )

    @work(thread=True)
    def run_scan(self, save_merge: str | None = None) -> None:
        worker = get_current_worker()

        if len(self.log_files) > 1:
            self.merge_log_files()
            if save_merge is not None:
                self.call_later(self.save, save_merge, self.line_count)
            return

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

        position = size
        line_count = 0

        for position, breaks in self.log_file.scan_line_breaks():
            line_count_thousands = line_count // 1000
            message = f"Scanning… ({line_count_thousands:,}K lines)- ESCAPE to cancel"

            self.post_message(ScanProgress(message, 1 - (position / size), position))
            if breaks:
                self.post_message(NewBreaks(self.log_file, breaks))
                line_count += len(breaks)
            if worker.is_cancelled:
                break
        self.post_message(ScanComplete(size, position))

    def merge_log_files(self) -> None:
        worker = get_current_worker()
        self._merge_lines = []
        merge_lines: list[tuple[float, int, LogFile]] = self._merge_lines
        append_meta = merge_lines.append

        for log_file in self.log_files:
            try:
                log_file.open(worker.cancelled_event)
            except Exception as error:
                self.notify(
                    f"Failed to open {log_file.name!r}; {error}", severity="error"
                )
            else:
                self._line_breaks[log_file] = []

        self.loading = False

        total_size = sum(log_file.size for log_file in self.log_files)
        position = 0

        for log_file in self.log_files:
            if not log_file.is_open:
                continue
            append = self._line_breaks[log_file].append
            for timestamps in log_file.scan_timestamps():
                break_position = 0
                for line_no, break_position, timestamp in timestamps:
                    if break_position:
                        append_meta((timestamp, line_no, log_file))
                        append(break_position)

                self.post_message(
                    ScanProgress(
                        f"Merging {log_file.name} - ESCAPE to cancel",
                        (position + break_position) / total_size,
                    )
                )
                if worker.is_cancelled:
                    self.post_message(
                        ScanComplete(total_size, position + break_position)
                    )
                    return

            position += log_file.size

        merge_lines.sort(key=itemgetter(0, 1))

        self.post_message(ScanComplete(total_size, total_size))

    @classmethod
    def _scan_file(
        cls, fileno: int, size: int, batch_time: float = 0.25
    ) -> Iterable[tuple[int, list[int]]]:
        """Find line breaks in a file.

        Yields lists of offsets.
        """
        if platform.system() == "Windows":
            log_mmap = mmap.mmap(fileno, size, access=mmap.ACCESS_READ)
        else:
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
                yield (position, batch)
                batch = []
        yield (0, batch)

    @work(thread=True)
    def save(self, path: str, line_count: int) -> None:
        """Save visible lines (used to export merged lines).

        Args:
            path: Path to save to.
            line_count: Number of lines to save.
        """
        try:
            with open(path, "w") as file_out:
                for line_no in range(line_count):
                    line = self.get_line_from_index_blocking(line_no)
                    if line:
                        file_out.write(f"{line}\n")
        except Exception as error:
            self.notify(f"Failed to save {path!r}; {error}", severity="error")
        else:
            self.notify(f"Saved merged log files to {path!r}")

    def get_log_file_from_index(self, index: int) -> tuple[LogFile, int]:
        if self._merge_lines is not None:
            try:
                _, index, log_file = self._merge_lines[index]
            except IndexError:
                return self.log_files[0], index
            return log_file, index
        return self.log_files[0], index

    def index_to_span(self, index: int) -> tuple[LogFile, int, int]:
        log_file, index = self.get_log_file_from_index(index)
        line_breaks = self._line_breaks.setdefault(log_file, [])
        if not line_breaks:
            return (log_file, self._scan_start, self._scan_start)
        index = clamp(index, 0, len(line_breaks))
        if index == 0:
            return (log_file, self._scan_start, line_breaks[0])
        start = line_breaks[index - 1]
        end = (
            line_breaks[index]
            if index < len(line_breaks)
            else max(0, self._scanned_size - 1)
        )
        return (log_file, start, end)

    def get_line_from_index_blocking(self, index: int) -> str | None:
        with self._lock:
            log_file, start, end = self.index_to_span(index)
            return log_file.get_line(start, end)

    def get_line_from_index(self, index: int) -> str | None:
        with self._lock:
            log_file, start, end = self.index_to_span(index)
            return self.get_line(log_file, index, start, end)

    def _get_line(self, log_file: LogFile, start: int, end: int) -> str:
        return log_file.get_line(start, end)

    def get_line(
        self, log_file: LogFile, index: int, start: int, end: int
    ) -> str | None:
        cache_key = (log_file, start, end)
        with self._lock:
            try:
                line = self._line_cache[cache_key]
            except KeyError:
                self._line_reader.request_line(log_file, index, start, end)
                return None
            return line

    def get_line_blocking(
        self, log_file: LogFile, index: int, start: int, end: int
    ) -> str:
        with self._lock:
            cache_key = (log_file, start, end)
            try:
                line = self._line_cache[cache_key]
            except KeyError:
                line = self._get_line(log_file, start, end)
                self._line_cache[cache_key] = line
            return line

    def get_text(
        self,
        line_index: int,
        abbreviate: bool = False,
        block: bool = False,
    ) -> tuple[str, Text, datetime | None]:
        log_file, start, end = self.index_to_span(line_index)
        cache_key = (log_file, start, end, abbreviate)
        try:
            line, text, timestamp = self._text_cache[cache_key]
        except KeyError:
            new_line: str | None
            if block:
                new_line = self.get_line_blocking(log_file, line_index, start, end)
            else:
                new_line = self.get_line(log_file, line_index, start, end)
            if new_line is None:
                return "", Text(""), None
            line = new_line
            timestamp, line, text = log_file.parse(line)
            if abbreviate and len(text) > MAX_LINE_LENGTH:
                text = text[:MAX_LINE_LENGTH] + "…"
            self._text_cache[cache_key] = (line, text, timestamp)
        return line, text.copy(), timestamp

    def get_timestamp(self, line_index: int) -> datetime | None:
        """Get a timestamp for the given line, or `None` if no timestamp detected.

        Args:
            line_index: Index of line.

        Returns:
            A datetime or `None`.
        """
        log_file, start, end = self.index_to_span(line_index)
        line = log_file.get_line(start, end)
        timestamp = log_file.timestamp_scanner.scan(line)
        return timestamp

    def on_unmount(self) -> None:
        self._line_reader.stop()
        self.log_file.close()

    def on_idle(self) -> None:
        self.update_virtual_size()

    def update_virtual_size(self) -> None:
        self.virtual_size = Size(
            self._max_width
            + (self.gutter_width if self.show_gutter or self.show_line_numbers else 0),
            self.line_count,
        )

    def render_lines(self, crop: Region) -> list[Strip]:
        self.update_virtual_size()

        page_height = self.scrollable_content_region.height
        scroll_y = self.scroll_offset.y
        line_count = self.line_count
        index_to_span = self.index_to_span
        for index in range(
            max(0, scroll_y - page_height),
            min(line_count, scroll_y + page_height + page_height),
        ):
            log_file_span = index_to_span(index)
            if log_file_span not in self._line_cache:
                log_file, *span = log_file_span
                self._line_reader.request_line(log_file, index, *span)
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

        log_file_span = self.index_to_span(index)

        is_pointer = self.pointer_line is not None and index == self.pointer_line
        cache_key = (*log_file_span, is_pointer, self.find)

        try:
            strip = self._render_line_cache[cache_key]
        except KeyError:
            line, text, timestamp = self.get_text(index, abbreviate=True, block=True)
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
            try:
                return (
                    re.match(
                        self.find,
                        line,
                        flags=0 if self.case_sensitive else re.IGNORECASE,
                    )
                    is not None
                )
            except Exception:
                self.notify("Regex is invalid!", severity="error")
                return True
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
            index_to_span = self.index_to_span
            with self._lock:
                for line_no in line_range:
                    log_file, start, end = index_to_span(line_no)
                    line = log_file.get_raw(start, end).decode(
                        "utf-8", errors="replace"
                    )
                    if check_match(line):
                        self.pointer_line = line_no
                        self.scroll_pointer_to_center()
                        return
            self.app.bell()
        else:
            self.pointer_line = next(
                iter(line_range), self.pointer_line or self.scroll_offset.y
            )
        if first:
            self.refresh()
        else:
            if self.pointer_line is not None and (
                self.pointer_line < scroll_y or self.pointer_line > max_scroll_y
            ):
                self.scroll_pointer_to_center()

    def scroll_pointer_to_center(self, animate: bool = True):
        if self.pointer_line is None:
            return
        y_offset = self.pointer_line - self.scrollable_content_region.height // 2
        scroll_distance = abs(y_offset - self.scroll_offset.y)
        self.scroll_to(
            y=y_offset,
            animate=animate and 100 > scroll_distance > 1,
            duration=0.2,
        )

    def watch_show_find(self, show_find: bool) -> None:
        self.clear_caches()
        if not show_find:
            self.pointer_line = None

    def watch_find(self, find: str) -> None:
        if not find:
            self.pointer_line = None

    def watch_case_sensitive(self) -> None:
        self.clear_caches()

    def watch_regex(self) -> None:
        self.clear_caches()

    def watch_pointer_line(
        self, old_pointer_line: int | None, pointer_line: int | None
    ) -> None:

        if old_pointer_line is not None:
            self.refresh_line(old_pointer_line)
        if pointer_line is not None:
            self.refresh_line(pointer_line)
        self.show_gutter = pointer_line is not None
        self.post_message(PointerMoved(pointer_line))

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
        if self.loading:
            return
        new_pointer_line = event.y + self.scroll_offset.y - self.gutter.top
        if new_pointer_line == self.pointer_line:
            self.post_message(FindDialog.SelectLine())
        self.pointer_line = new_pointer_line
        self.post_message(TailFile(False))

    def action_select(self):
        if self.pointer_line is None:
            self.pointer_line = self.scroll_offset.y
        else:
            self.post_message(FindDialog.SelectLine())

    def action_dismiss(self):
        if self.initial_scan_worker is not None and self.initial_scan_worker.is_running:
            self.initial_scan_worker.cancel()
            self.notify(
                "Stopped scanning. Some lines may not be available.", severity="warning"
            )
        else:
            self.post_message(DismissOverlay())

    # @work(thread=True)
    def action_navigate(self, steps: int, unit: Literal["m", "h", "d"]) -> None:

        initial_line_no = line_no = (
            self.scroll_offset.y if self.pointer_line is None else self.pointer_line
        )

        count = 0
        # If the current line doesn't have a timestamp, try to find the next one
        while (timestamp := self.get_timestamp(line_no)) is None:
            line_no += 1
            count += 1
            if count >= self.line_count or count > 10:
                self.app.bell()
                return

        direction = +1 if steps > 0 else -1
        line_no += direction

        if unit == "m":
            target_timestamp = timestamp + timedelta(minutes=steps)
        elif unit == "h":
            target_timestamp = timestamp + timedelta(hours=steps)
        elif unit == "d":
            target_timestamp = timestamp + timedelta(hours=steps * 24)

        if direction == +1:
            line_count = self.line_count
            while line_no < line_count:
                timestamp = self.get_timestamp(line_no)
                if timestamp is not None and timestamp >= target_timestamp:
                    break
                line_no += 1
        else:
            while line_no > 0:
                timestamp = self.get_timestamp(line_no)
                if timestamp is not None and timestamp <= target_timestamp:
                    break
                line_no -= 1

        self.pointer_line = line_no
        self.scroll_pointer_to_center(animate=abs(initial_line_no - line_no) < 100)

    def watch_tail(self, tail: bool) -> None:
        self.set_class(tail, "-tail")
        if tail:
            self.update_line_count()
            self.scroll_to(y=self.max_scroll_y, animate=False)
            if tail:
                self.pointer_line = None

    def update_line_count(self) -> None:
        line_count = len(self._line_breaks.get(self.log_file, []))
        line_count = max(1, line_count)
        self._line_count = line_count

    @on(NewBreaks)
    def on_new_breaks(self, event: NewBreaks) -> None:
        line_breaks = self._line_breaks.setdefault(event.log_file, [])
        first = not line_breaks
        event.stop()
        self._scanned_size = max(self._scanned_size, event.scanned_size)

        if not self.tail and event.tail:
            self.post_message(PendingLines(len(line_breaks) - self._line_count + 1))

        line_breaks.extend(event.breaks)
        if not event.tail:
            line_breaks.sort()

        pointer_distance_from_end = (
            None
            if self.pointer_line is None
            else self.virtual_size.height - self.pointer_line
        )
        self.loading = False

        if not event.tail or self.tail or first:
            self.update_line_count()

        if self.tail:
            if self.pointer_line is not None and pointer_distance_from_end is not None:
                self.pointer_line = self.virtual_size.height - pointer_distance_from_end
            self.update_virtual_size()
            self.scroll_to(y=self.max_scroll_y, animate=False, force=True)

    def watch_scroll_y(self, old_value: float, new_value: float) -> None:
        self.post_message(PointerMoved(self.pointer_line))
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
        if len(self.log_files) == 1 and self.can_tail:
            self.start_tail()

    @on(ScanProgress)
    def on_scan_progress(self, event: ScanProgress):
        if event.scan_start is not None:
            self._scan_start = event.scan_start

    @on(LineRead)
    def on_line_read(self, event: LineRead) -> None:
        event.stop()
        start = event.start
        end = event.end
        log_file = event.log_file
        self._render_line_cache.discard((log_file, start, end, True, self.find))
        self._render_line_cache.discard((log_file, start, end, False, self.find))
        self._line_cache[(log_file, start, end)] = event.line
        self._text_cache.discard((log_file, start, end, False))
        self._text_cache.discard((log_file, start, end, True))
        self.refresh_lines(event.index, 1)
