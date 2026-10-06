from __future__ import annotations
from datetime import datetime
import json

from rich.json import JSON
from rich.text import Text

from textual.app import ComposeResult
from textual.containers import ScrollableContainer, Horizontal

from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Label, Static

from toolong.messages import DismissOverlay


class WordWrapButton(Label):
    """Clickable toggle button for word wrap."""

    DEFAULT_CSS = """
    WordWrapButton {
        color: $success;
        &:light {
            color: $primary;
        }
        padding: 0 1 0 0;
        &:hover {
            text-style: bold underline;
        }
        &.active {
            background: $success 25%;
        }
    }
    """

    word_wrap: reactive[bool] = reactive(True)

    def render(self) -> str:
        check = "✓" if self.word_wrap else " "
        return f"[reverse] {check} [/reverse] Wrap"

    def watch_word_wrap(self, word_wrap: bool) -> None:
        self.set_class(word_wrap, "active")

    def on_click(self) -> None:
        panel = self.screen.query_one(LinePanel)
        panel.word_wrap = not panel.word_wrap


class CloseButton(Label):
    """Clickable button to close the detail panel."""

    DEFAULT_CSS = """
    CloseButton {
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

    def render(self) -> str:
        return "[reverse] X [/reverse] Close"

    def on_click(self) -> None:
        self.post_message(DismissOverlay())


class PanelToolbar(Horizontal):
    """Toolbar at the top of the detail panel."""

    DEFAULT_CSS = """
    PanelToolbar {
        height: 1;
        width: 1fr;
        dock: top;
        background: $surface;
        padding: 0 1;
        WordWrapButton {
            dock: right;
        }
    }
    """

    def compose(self) -> ComposeResult:
        yield CloseButton()
        yield WordWrapButton()


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
        .nl {
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

        if "\\n" in self.text.plain:
            lines = self.text.split("\\n")
            text = Text("\n", no_wrap=True).join(lines)
            yield Label(text, classes="nl")
        else:
            yield Label(self.text)


class LinePanel(ScrollableContainer):
    DEFAULT_CSS = """
    LinePanel {
        background: $panel;        
        overflow-y: auto;
        overflow-x: auto;
        scrollbar-gutter: stable;
        &.word-wrap {
            overflow-x: hidden;
            LineDisplay {
                width: 1fr;
                Label {
                    width: 1fr;
                }
                .json {
                    width: 1fr;
                }
                .nl {
                    width: 1fr;
                }
            }
        }
    }
    """

    word_wrap: reactive[bool] = reactive(True)

    def compose(self) -> ComposeResult:
        yield PanelToolbar()

    def watch_word_wrap(self, word_wrap: bool) -> None:
        self.set_class(word_wrap, "word-wrap")
        self.query_one(WordWrapButton).word_wrap = word_wrap

    def on_mount(self) -> None:
        self.set_class(self.word_wrap, "word-wrap")

    async def update(self, line: str, text: Text, timestamp: datetime | None) -> None:
        with self.app.batch_update():
            await self.query(LineDisplay).remove()
            await self.mount(LineDisplay(line, text, timestamp))
