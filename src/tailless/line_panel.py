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
        Label {
            width: 1fr;
        }
    }
    """

    def __init__(self, line: str, text: Text, timestamp: datetime | None) -> None:
        self.line = line
        self.text = text
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Label(self.text)


class LinePanel(Widget):
    DEFAULT_CSS = """
    LinePanel {
        background: $panel;
        padding: 1 2;
    }
    """
    line_no = reactive(0)

    def __init__(self, mapped_file: MappedFile) -> None:
        self.mapped_file = mapped_file
        super().__init__()

    def compose(self) -> ComposeResult:
        line, text, timestamp = self.mapped_file.get_text(self.line_no)
        yield LineDisplay(line, text, timestamp)

    async def watch_line_no(self, line_no: int) -> None:
        line, text, timestamp = self.mapped_file.get_text(self.line_no)
        with self.app.batch_update():
            await self.query_one(LineDisplay).remove()
            await self.mount(LineDisplay(line, text, timestamp))
