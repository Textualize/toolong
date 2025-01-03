from __future__ import annotations

from pathlib import Path
from datetime import datetime
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.dom import NoScreen
from textual import events
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Label
from asyncio import Lock
import json

from toolong.messages import (
    DismissOverlay,
    Goto,
    PendingLines,
    PointerMoved,
    ScanComplete,
    TailFile,
)
from toolong.find_dialog import FindDialog
from toolong.line_panel import LinePanel
from toolong.watcher import WatcherBase
from toolong.log_lines import LogLines
from toolong.eliot_view import EliotView
from toolong.scan_progress_bar import ScanProgressBar

SPLIT_REGEX = r"[\s/\[\]]"
MAX_DETAIL_LINE_LENGTH = 100_000

class InfoOverlay(Widget):
    """Displays text under the lines widget when there are new lines."""

    DEFAULT_CSS = """
    InfoOverlay {
        display: none;
        dock: bottom;        
        layer: overlay;
        width: 1fr;
        visibility: hidden;        
        offset-y: -1;
        text-style: bold;
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
    tail = reactive(False)

    def compose(self) -> ComposeResult:
        self.tooltip = "Click to tail file"
        with Horizontal():
            yield Label("")

    def watch_message(self, message: str) -> None:
        self.display = bool(message.strip())
        self.query_one(Label).update(message)

    def watch_tail(self, tail: bool) -> None:
        if not tail:
            self.message = ""
        self.display = bool(self.message.strip() and not tail)

    def on_click(self) -> None:
        self.post_message(TailFile())

class FooterKey(Label):
    """Displays a clickable label for a key."""

    DEFAULT_CSS = """
    FooterKey {
        color: $success;
        &:light {
            color: $primary;
        }
        padding: 0 1 0 0;        
        &:hover {
            text-style: bold underline;                        
        }
    }
    """
    DEFAULT_CLASSES = "key"

    def __init__(self, key: str, key_display: str, description: str) -> None:
        self.key = key
        self.key_display = key_display
        self.description = description
        super().__init__()

    def render(self) -> str:
        return f"[reverse]{self.key_display}[/reverse] {self.description}"

    async def on_click(self) -> None:
        await self.app.check_bindings(self.key)

class MetaLabel(Label):
    """Label for metadata that can be clicked to goto."""

    DEFAULT_CSS = """
    MetaLabel {
        margin-left: 1;
    }
    MetaLabel:hover {
        text-style: underline;
    }
    """

    def on_click(self) -> None:
        self.post_message(Goto())

class LogFooter(Widget):
    """Shows a footer with information about the file and keys."""

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
        
        .key {
            color: $warning;
        }

        .meta {
            width: auto;
            height: 1;
            color: $success;
            padding: 0 1 0 0;
        }
        
        .tail {
            padding: 0 1;
            margin: 0 1;
            background: $success 15%;
            color: $success;
            text-style: bold;
            display: none;
            &.on {
                display: block;
            }
        }
    }
    """
    line_no: reactive[int | None] = reactive(None)
    filename: reactive[str] = reactive("")
    timestamp: reactive[datetime | None] = reactive(None)
    tail: reactive[bool] = reactive(False)
    can_tail: reactive[bool] = reactive(False)

    def __init__(self) -> None:
        self.lock = Lock()
        super().__init__()

    def compose(self) -> ComposeResult:
        with Horizontal(classes="key-container"):
            pass
        yield Label("TAIL", classes="tail")
        yield MetaLabel("", classes="meta")

    async def mount_keys(self) -> None:
        try:
            if self.screen != self.app.screen:
                return
        except NoScreen:
            pass
        async with self.lock:
            with self.app.batch_update():
                key_container = self.query_one(".key-container")
                await key_container.query("*").remove()
                bindings = [
                    binding
                    for (_, binding) in self.app.namespace_bindings.values()
                    if binding.show
                ]

                await key_container.mount_all(
                    [
                        FooterKey(
                            binding.key,
                            binding.key_display or binding.key,
                            binding.description,
                        )
                        for binding in bindings
                        if binding.action != "toggle_tail"
                        or (binding.action == "toggle_tail" and self.can_tail)
                    ]
                )

    async def on_mount(self):
        self.watch(self.screen, "focused", self.mount_keys)
        self.watch(self.screen, "stack_updates", self.mount_keys)
        self.call_after_refresh(self.mount_keys)

    def update_meta(self) -> None:
        meta: list[str] = []
        if self.filename:
            meta.append(self.filename)
        if self.timestamp is not None:
            meta.append(f"{self.timestamp:%x %X}")
        if self.line_no is not None:
            meta.append(f"{self.line_no + 1}")

        meta_line = " • ".join(meta)
        self.query_one(".meta", Label).update(meta_line)

    def watch_tail(self, tail: bool) -> None:
        self.query(".tail").set_class(tail and self.can_tail, "on")

    async def watch_can_tail(self, can_tail: bool) -> None:
        await self.mount_keys()

    def watch_filename(self, filename: str) -> None:
        self.update_meta()

    def watch_line_no(self, line_no: int | None) -> None:
        self.update_meta()

    def watch_timestamp(self, timestamp: datetime | None) -> None:
        self.update_meta()

class LogView(Horizontal):
    """Widget that contains log lines and associated widgets."""

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
        Binding("ctrl+t", "toggle_tail", "Tail", key_display="^t"),
        Binding("ctrl+l", "toggle('show_line_numbers')", "Line nos.", key_display="^l"),
        Binding("ctrl+f", "show_find_dialog", "Find", key_display="^f"),
        Binding("slash", "show_find_dialog", "Find", key_display="^f", show=False),
        Binding("ctrl+g", "goto", "Go to", key_display="^g"),
    ]

    show_line_numbers: reactive[bool] = reactive(False)
    show_find: reactive[bool] = reactive(False)
    show_panel: reactive[bool] = reactive(False)
    tail: reactive[bool] = reactive(False)
    can_tail: reactive[bool] = reactive(True)

    def __init__(self, file_paths: list[str], watcher: WatcherBase, can_tail: bool = True) -> None:
        super().__init__()
        self.file_paths = file_paths
        self.watcher = watcher
        self.eliot_view: EliotView | None = None
        self.can_tail = can_tail

    def _is_eliot_log(self, line: str) -> bool:
        """Check if a line is an Eliot log entry."""
        try:
            data = json.loads(line)
            return all(key in data for key in ("task_uuid", "task_level", "action_type"))
        except (json.JSONDecodeError, KeyError):
            return False

    def compose(self) -> ComposeResult:
        """Create child widgets."""
        yield ScanProgressBar()

        # Check first line of each file to determine if it's an Eliot log
        is_eliot = False
        for path in self.file_paths:
            try:
                with open(path) as f:
                    first_line = f.readline().strip()
                    if first_line and self._is_eliot_log(first_line):
                        is_eliot = True
                        break
            except (IOError, OSError):
                continue

        if is_eliot:
            # For Eliot logs, use only the tree view
            self.eliot_view = EliotView()
            self.eliot_view.file_paths = self.file_paths
            yield self.eliot_view
        else:
            # For regular logs, use the full log view functionality
            log_lines = LogLines(self.watcher, self.file_paths)
            yield log_lines.data_bind(
                LogView.tail,
                LogView.show_line_numbers,
                LogView.show_find,
                LogView.can_tail,
            )
            yield LinePanel()
            yield FindDialog(log_lines._suggester)
            yield InfoOverlay().data_bind(LogView.tail)
            yield LogFooter().data_bind(LogView.tail, LogView.can_tail)

    @on(FindDialog.Update)
    def filter_dialog_update(self, event: FindDialog.Update) -> None:
        if not self.eliot_view:
            log_lines = self.query_one(LogLines)
            log_lines.find = event.find
            log_lines.regex = event.regex
            log_lines.case_sensitive = event.case_sensitive

    async def watch_show_find(self, show_find: bool) -> None:
        if not self.is_mounted or self.eliot_view:
            return
        filter_dialog = self.query_one(FindDialog)
        filter_dialog.display = show_find
        if show_find:
            filter_dialog.focus_input()
        else:
            self.query_one(LogLines).focus()

    async def watch_show_panel(self, show_panel: bool) -> None:
        if not self.eliot_view:
            self.set_class(show_panel, "show-panel")
            await self.update_panel()

    @on(FindDialog.Dismiss)
    def dismiss_filter_dialog(self, event: FindDialog.Dismiss) -> None:
        if not self.eliot_view:
            self.show_find = False
            event.stop()

    @on(FindDialog.MovePointer)
    def move_pointer(self, event: FindDialog.MovePointer) -> None:
        if not self.eliot_view:
            event.stop()
            self.query_one(LogLines).advance_search(event.direction)

    @on(FindDialog.SelectLine)
    def select_line(self) -> None:
        if not self.eliot_view:
            self.show_panel = not self.show_panel

    @on(DismissOverlay)
    def dismiss_overlay(self) -> None:
        if not self.eliot_view:
            if self.show_find:
                self.show_find = False
            elif self.show_panel:
                self.show_panel = False
            else:
                setattr(self.query_one(LogLines), 'pointer_line', None)

    @on(TailFile)
    def on_tail_file(self, event: TailFile) -> None:
        if not self.eliot_view:
            self.tail = True
            event.stop()

    async def update_panel(self) -> None:
        if not self.show_panel or self.eliot_view is not None:
            return
        pointer_line = self.query_one(LogLines).pointer_line
        if pointer_line is not None:
            panel = self.query_one(LinePanel)
            log_lines = self.query_one(LogLines)
            line, text, timestamp = log_lines.get_text(
                pointer_line,
                block=True,
                abbreviate=True,
                max_line_length=MAX_DETAIL_LINE_LENGTH,
            )
            await panel.update(line, text, timestamp)

    @on(PointerMoved)
    async def pointer_moved(self, event: PointerMoved):
        if not self.eliot_view:
            if event.pointer_line is None:
                self.show_panel = False
            if self.show_panel:
                await self.update_panel()

            log_lines = self.query_one(LogLines)
            pointer_line = log_lines.scroll_offset.y if event.pointer_line is None else event.pointer_line
            log_file, _, _ = log_lines.index_to_span(pointer_line)
            log_footer = self.query_one(LogFooter)
            log_footer.line_no = pointer_line
            if len(log_lines.log_files) > 1:
                log_footer.filename = log_file.name
            log_footer.timestamp = log_lines.get_timestamp(pointer_line)

    @on(PendingLines)
    def on_pending_lines(self, event: PendingLines) -> None:
        if not self.eliot_view and not self.tail:
            info = self.query_one(InfoOverlay)
            info.message = f"{event.count} new line{'s' if event.count > 1 else ''}"

    @on(ScanComplete)
    async def on_scan_complete(self, event: ScanComplete) -> None:
        try:
            progress_bar = self.query_one(ScanProgressBar)
            if progress_bar is not None:
                progress_bar.remove()
        except Exception:
            pass  # Progress bar might already be removed

        if self.eliot_view is not None:
            self.eliot_view.tree.loading = False
            self.eliot_view.tree.remove_class("-scanning")
        else:
            log_lines = self.query_one(LogLines)
            log_lines.loading = False
            log_lines.remove_class("-scanning")
            self.post_message(PointerMoved(log_lines.pointer_line))
            self.tail = True
            self.query_one(LogFooter).can_tail = True

    @on(events.DescendantFocus)
    @on(events.DescendantBlur)
    def on_descendant_focus(self, event: events.DescendantBlur) -> None:
        focused = self.screen.focused
        self.set_class(
            isinstance(focused, (LogLines if not self.eliot_view else EliotView)),
            "lines-view" if not self.eliot_view else "tree-view"
        )

    def action_toggle_tail(self) -> None:
        if not self.eliot_view and self.can_tail:
            self.tail = not self.tail

    def action_show_find_dialog(self) -> None:
        if not self.eliot_view:
            self.show_find = True

    def action_goto(self) -> None:
        if not self.eliot_view:
            from toolong.goto_screen import GotoScreen
            self.app.push_screen(GotoScreen(self.query_one(LogLines)))