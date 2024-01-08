from textual.app import App, ComposeResult
from textual.widgets import Footer, TabbedContent, TabPane

from .log_view import LogView


class UI(App):
    def __init__(self, file_paths: list[str]) -> None:
        self.file_paths = file_paths
        super().__init__()

    def compose(self) -> ComposeResult:
        with TabbedContent():
            for path in self.file_paths:
                with TabPane(path):
                    yield LogView(path)
        yield Footer()
