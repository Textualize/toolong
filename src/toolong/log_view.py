from __future__ import annotations

from asyncio import Lock
from datetime import datetime

from rich.text import Text

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.dom import NoScreen
from textual import events
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Label


from toolong.scan_progress_bar import ScanProgressBar

from toolong.messages import (
    DismissOverlay,
    Goto,
    PendingLines,
    PointerMoved,
    ScanComplete,
    ScanProgress,
    TailFile,
)
from toolong.find_dialog import FindDialog
from toolong.line_panel import LinePanel
from toolong.watcher import WatcherBase
from toolong.log_lines import LogLines


SPLIT_REGEX = r"[\s/\[\]]"


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

    show_find: reactive[bool] = reactive(False)
    show_panel: reactive[bool] = reactive(False)
    show_line_numbers: reactive[bool] = reactive(False)
    tail: reactive[bool] = reactive(False)
    can_tail: reactive[bool] = reactive(True)

    def __init__(
        self, file_paths: list[str], watcher: WatcherBase, can_tail: bool = True
    ) -> None:
        self.file_paths = file_paths
        self.watcher = watcher
        super().__init__()
        # Need a better solution for this
        self.call_later(setattr, self, "can_tail", can_tail)

    def compose(self) -> ComposeResult:
        yield (
            log_lines := LogLines(self.watcher, self.file_paths).data_bind(
                LogView.tail,
                LogView.show_line_numbers,
                LogView.show_find,
                LogView.can_tail,
            )
        )
        yield LinePanel()
        yield FindDialog(log_lines._suggester)
        yield InfoOverlay().data_bind(LogView.tail)
        yield LogFooter().data_bind(LogView.tail, LogView.can_tail)

    @on(FindDialog.Update)
    def filter_dialog_update(self, event: FindDialog.Update) -> None:
        log_lines = self.query_one(LogLines)
        log_lines.find = event.find
        log_lines.regex = event.regex
        log_lines.case_sensitive = event.case_sensitive

    async def watch_show_find(self, show_find: bool) -> None:
        if not self.is_mounted:
            return
        filter_dialog = self.query_one(FindDialog)
        filter_dialog.set_class(show_find, "visible")
        if show_find:
            filter_dialog.focus_input()
        else:
            self.query_one(LogLines).focus()

    async def watch_show_panel(self, show_panel: bool) -> None:
        self.set_class(show_panel, "show-panel")
        await self.update_panel()

    @on(FindDialog.Dismiss)
    def dismiss_filter_dialog(self, event: FindDialog.Dismiss) -> None:
        event.stop()
        self.show_find = False

    @on(FindDialog.MovePointer)
    def move_pointer(self, event: FindDialog.MovePointer) -> None:
        event.stop()
        log_lines = self.query_one(LogLines)
        log_lines.advance_search(event.direction)

    @on(FindDialog.SelectLine)
    def select_line(self) -> None:
        self.show_panel = not self.show_panel

    @on(DismissOverlay)
    def dismiss_overlay(self) -> None:
        if self.show_find:
            self.show_find = False
        elif self.show_panel:
            self.show_panel = False
        else:
            self.query_one(LogLines).pointer_line = None

    @on(TailFile)
    def on_tail_file(self, event: TailFile) -> None:
        self.tail = event.tail
        event.stop()

    async def update_panel(self) -> None:
        if not self.show_panel:
            return
        pointer_line = self.query_one(LogLines).pointer_line
        if pointer_line is not None:
            line, text, timestamp = self.query_one(LogLines).get_text(
                pointer_line, block=True
            )
            await self.query_one(LinePanel).update(line, text, timestamp)

    @on(PointerMoved)
    async def pointer_moved(self, event: PointerMoved):
        if event.pointer_line is None:
            self.show_panel = False
        if self.show_panel:
            await self.update_panel()

        log_lines = self.query_one(LogLines)
        pointer_line = (
            log_lines.scroll_offset.y
            if event.pointer_line is None
            else event.pointer_line
        )
        log_file, _, _ = log_lines.index_to_span(pointer_line)
        log_footer = self.query_one(LogFooter)
        log_footer.line_no = pointer_line
        if len(log_lines.log_files) > 1:
            log_footer.filename = log_file.name

        timestamp = log_lines.get_timestamp(pointer_line)
        log_footer.timestamp = timestamp

    @on(PendingLines)
    def on_pending_lines(self, event: PendingLines) -> None:
        if self.app._exit:
            return
        event.stop()
        self.query_one(InfoOverlay).message = f"+{event.count:,} lines"

    @on(ScanProgress)
    def on_scan_progress(self, event: ScanProgress):
        event.stop()
        scan_progress_bar = self.query_one(ScanProgressBar)
        scan_progress_bar.message = event.message
        scan_progress_bar.complete = event.complete

    @on(ScanComplete)
    async def on_scan_complete(self, event: ScanComplete) -> None:
        self.query_one(ScanProgressBar).remove()
        log_lines = self.query_one(LogLines)
        log_lines.loading = False
        self.query_one("LogLines").remove_class("-scanning")
        self.post_message(PointerMoved(log_lines.pointer_line))
        self.tail = True

        footer = self.query_one(LogFooter)
        footer.call_after_refresh(footer.mount_keys)

    @on(events.DescendantFocus)
    @on(events.DescendantBlur)
    def on_descendant_focus(self, event: events.DescendantBlur) -> None:
        self.set_class(isinstance(self.screen.focused, LogLines), "lines-view")

    def action_toggle_tail(self) -> None:
        if not self.can_tail:
            self.notify("Can't tail merged files", title="Tail", severity="error")
        else:
            self.tail = not self.tail

    def action_show_find_dialog(self) -> None:
        find_dialog = self.query_one(FindDialog)
        if not self.show_find or not any(
            input.has_focus for input in find_dialog.query("Input")
        ):
            self.show_find = True
            find_dialog.focus_input()

    @on(Goto)
    def on_goto(self) -> None:
        self.action_goto()

    def action_goto(self) -> None:
        from toolong.goto_screen import GotoScreen

        self.app.push_screen(GotoScreen(self.query_one(LogLines)))
