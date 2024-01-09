from dataclasses import dataclass
from typing import Any, Coroutine

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.suggester import Suggester
from textual.widget import Widget
from textual.widgets import Input, Checkbox


class FilterDialog(Widget, can_focus_children=True):
    DEFAULT_CSS = """
    FilterDialog {
        layout: horizontal;
        dock: top; 
        padding-top: 1;                       
        width: 1fr;
        height: auto;
        max-height: 70%;
        display: none;
        & #find {
            width: 1fr;
        }
        &.visible {
            display: block;
        }
    }    
    """
    BINDINGS = [
        Binding("escape", "dismiss_find", "Dismiss"),
    ]
    DEFAULT_CLASSES = "float"
    BORDER_TITLE = "Find"

    @dataclass
    class Update(Message):
        find: str
        regex: bool
        case_sensitive: bool

    class Dismiss(Message):
        pass

    def __init__(self, suggester: Suggester) -> None:
        self.suggester = suggester
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Find", id="find", suggester=self.suggester)
        yield Checkbox("Case sensitive", id="case-sensitive")
        yield Checkbox("Regex", id="regex")

    @on(Input.Changed)
    @on(Checkbox.Changed)
    def input_change(self, event: Input.Changed) -> None:
        event.stop()
        self.post_update()

    def post_update(self) -> None:
        update = FilterDialog.Update(
            find=self.query_one("#find", Input).value,
            regex=self.query_one("#regex", Checkbox).value,
            case_sensitive=self.query_one("#case-sensitive", Checkbox).value,
        )
        self.post_message(update)

    def action_dismiss_find(self) -> None:
        self.post_message(FilterDialog.Dismiss())

    def allow_focus_children(self) -> bool:
        return self.has_class("visible")
