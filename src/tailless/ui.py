from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.lazy import Lazy
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import TabbedContent, TabPane

from .log_lines import LogLines

from .log_view import LogView
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

    def compose(self) -> ComposeResult:
        assert isinstance(self.app, UI)
        with TabbedContent():
            if self.app.merge:
                tab_name = " + ".join(Path(path).name for path in self.app.file_paths)
                with TabPane(tab_name):
                    yield Lazy(LogView(self.app.file_paths, self.app.watcher))
            else:
                for path in self.app.file_paths:
                    with TabPane(path):
                        yield Lazy(LogView([path], self.app.watcher))

    def on_mount(self) -> None:
        assert isinstance(self.app, UI)
        self.query("TabbedContent Tabs").set(display=len(self.query(TabPane)) > 1)
        active_pane = self.query_one(TabbedContent).active_pane
        if active_pane is not None:
            active_pane.query("LogView > LogLines").focus()


class UI(App):

    @classmethod
    def sort_paths(cls, paths: list[str]) -> list[str]:
        def key(path) -> list:
            return [
                int(token) if token.isdigit() else token.lower()
                for token in path.split("/")[-1].split(".")
            ]

        return sorted(paths, key=key)

    def __init__(self, file_paths: list[str], merge: bool = False) -> None:
        self.file_paths = self.sort_paths(file_paths)
        self.merge = merge
        self.watcher = Watcher()
        super().__init__()

    async def on_mount(self) -> None:
        await self.push_screen(LogScreen())
        self.screen.query("LogLines").focus()
        self.watcher.start()

    def on_unmount(self) -> None:
        self.watcher.close()
