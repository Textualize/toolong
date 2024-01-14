from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, TabbedContent, TabPane

from .log_view import LogView
from .watcher import Watcher


class LogScreen(Screen):
    CSS = """
    LogScreen {
        
        & TabPane {           
            padding: 0;
        }
    }
    """

    BINDINGS = [
        Binding("ctrl+f", "toggle_find", "Find"),
        Binding("ctrl+t", "toggle_timestamps", "Timestamps"),
    ]

    def compose(self) -> ComposeResult:
        assert isinstance(self.app, UI)
        with TabbedContent():
            for path in self.app.file_paths:
                with TabPane(path):
                    yield LogView(path)
        yield Footer()

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


class UI(App):
    CSS = """
    Screen {

    }    
    """

    def __init__(self, file_paths: list[str]) -> None:
        self.file_paths = file_paths
        self.watcher = Watcher()
        super().__init__()

    def on_mount(self) -> None:
        self.push_screen(LogScreen())
        self.watcher.start()

    def on_unmount(self) -> None:
        self.watcher.close()
