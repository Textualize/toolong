from datetime import datetime

from rich.text import Text

from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Label

from .mapped_file import MappedFile


class LineDisplay(Widget):
    DEFAULT_CSS = """
    LineDisplay {
        border: panel $primary;
        border-title-color: $foreground;
        padding: 1;
        Label {
            width: 1fr;
        }
    }
    """

    def __init__(self, line: str, text: Text, timestamp: datetime | None) -> None:
        self.line = line
        self.text = text
        super().__init__()
        if timestamp is not None:
            self.border_title = f"🕒 {timestamp.ctime()}"

    def compose(self) -> ComposeResult:
        yield Label(self.text)


class LinePanel(Widget):
    DEFAULT_CSS = """
    LinePanel {
        background: $panel;
        padding: 1 0;
    }
    """

    def update(self, line: str, text: Text, timestamp: datetime | None) -> None:
        with self.app.batch_update():
            self.query(LineDisplay).remove()
            self.mount(LineDisplay(line, text, timestamp))
