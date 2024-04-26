from __future__ import annotations
from datetime import datetime
import json
import re

from rich.json import JSON
from rich.text import Text

from textual.app import ComposeResult
from textual.containers import ScrollableContainer

from textual.widget import Widget
from textual.widgets import Label, Static


class LineDisplay(Widget):
    DEFAULT_CSS = """
    LineDisplay {        
        padding: 0 1;
        margin: 1 0;
        width: auto;
        height: auto;        
        Label {
            width: 1fr;
        }  
        .json {
            width: auto;        
        }      
    }
    """

    def __init__(self, line: str, text: Text, timestamp: datetime | None) -> None:
        self.line = line
        self.text = text
        self.timestamp = timestamp
        super().__init__()

    def compose(self) -> ComposeResult:
        try:
            json_data = json.loads(self.line)
        except Exception:
            pass
        else:
            yield Static(JSON.from_data(json_data), expand=True, classes="json")
            return
        if self.app.new_lines:
            self.text._text[0] = re.sub("\\\\n", "\n", self.text._text[0])
        yield Label(self.text)


class LinePanel(ScrollableContainer):
    DEFAULT_CSS = """
    LinePanel {
        background: $panel;        
        overflow-y: auto;
        border: blank transparent;                
        scrollbar-gutter: stable;
        &:focus {
            border: heavy $accent;
        }
    }
    """

    async def update(self, line: str, text: Text, timestamp: datetime | None) -> None:
        with self.app.batch_update():
            await self.query(LineDisplay).remove()
            await self.mount(LineDisplay(line, text, timestamp))
