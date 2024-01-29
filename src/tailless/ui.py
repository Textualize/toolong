from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.lazy import Lazy
from textual.screen import Screen
from textual.widgets import Footer, TabbedContent, TabPane

from .log_view import LogView, LogFooter
from .watcher import Watcher


class LogScreen(Screen):
    CSS = """
    LogScreen {
        layers: overlay;
        & TabPane {           
            padding: 0;
        }

        & Tabs:focus Underline > .underline--bar {
            color: $accent;
        }
        
        Underline > .underline--bar {
            color: $panel;
        }
    }

    """

    BINDINGS = [
        Binding("ctrl+f", "toggle_find", "Find"),
        Binding("ctrl+t", "toggle_timestamps", "Timestamps"),
        Binding("ctrl+l", "toggle_line_numbers", "Line numbers"),
    ]

    def compose(self) -> ComposeResult:
        assert isinstance(self.app, UI)
        with TabbedContent():
            for path in self.app.file_paths:
                with TabPane(path):
                    yield Lazy(LogView(path, self.app.watcher))

    def on_mount(self) -> None:
        self.query_one(TabbedContent).active_pane.query("LogView > LogLines").focus()

    def action_toggle_find(self) -> None:
        tabbed_content = self.query_one(TabbedContent)
        pane = tabbed_content.get_pane(tabbed_content.active)
        log_view = pane.query_one(LogView)
        log_view.show_find = not log_view.show_find

    def action_toggle_timestamps(self):
        tabbed_content = self.query_one(TabbedContent)
        pane = tabbed_content.get_pane(tabbed_content.active)
        log_view = pane.query_one(LogView)
        log_view.show_timestamps = not log_view.show_timestamps

    def action_toggle_line_numbers(self):
        tabbed_content = self.query_one(TabbedContent)
        pane = tabbed_content.get_pane(tabbed_content.active)
        log_view = pane.query_one("LogLines")
        log_view.show_line_numbers = not log_view.show_line_numbers


class UI(App):
    CSS = """
    Screen {

    }    
    """

    @classmethod
    def sort_paths(cls, paths: list[str]) -> None:
        def key(path) -> list:
            return [
                int(token) if token.isdigit() else token
                for token in path.split("/")[-1].split(".")
            ]

        return sorted(paths, key=key)

    def __init__(self, file_paths: list[str]) -> None:
        self.file_paths = self.sort_paths(file_paths)
        self.watcher = Watcher()
        super().__init__()

    async def on_mount(self) -> None:
        await self.push_screen(LogScreen())
        self.screen.query("LogLines").first().focus()
        self.watcher.start()

    def on_unmount(self) -> None:
        self.watcher.close()
