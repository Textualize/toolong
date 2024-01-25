from datetime import datetime

from rich.text import Text

from textual.app import ComposeResult
from textual.containers import VerticalScroll

from textual.widget import Widget
from textual.widgets import Label


class LineDisplay(Widget):
    DEFAULT_CSS = """
    LineDisplay {        
        padding: 0 1;
        margin: 1 0;
        height: auto;
        Label {
            width: 1fr;
        }        
    }
    """

    def __init__(self, line: str, text: Text, timestamp: datetime | None) -> None:
        self.line = line
        self.text = text
        self.timestamp = timestamp
        super().__init__()

    def compose(self) -> ComposeResult:
        if self.timestamp is not None:
            yield Label(f"🕒 {self.timestamp.ctime()}")
        yield Label(self.text)


class LinePanel(VerticalScroll):
    DEFAULT_CSS = """
    LinePanel {
        background: $panel;        
        overflow-y: auto;
        border: blank transparent;                

        &:focus {
            border: heavy $accent;
        }
    }
    """

    async def update(self, line: str, text: Text, timestamp: datetime | None) -> None:
        with self.app.batch_update():
            await self.query(LineDisplay).remove()
            await self.mount(LineDisplay(line, text, timestamp))
