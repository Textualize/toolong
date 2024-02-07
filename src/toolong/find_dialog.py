from dataclasses import dataclass

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.suggester import Suggester
from textual.widget import Widget
from textual.widgets import Input, Checkbox


class FindDialog(Widget, can_focus_children=True):
    DEFAULT_CSS = """
    FindDialog {
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
        Binding("escape", "dismiss_find", "Dismiss", key_display="esc"),
        Binding("down", "pointer_down", "Next", key_display="↓"),
        Binding("up", "pointer_up", "Previous", key_display="↑"),
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

    @dataclass
    class MovePointer(Message):
        direction: int = 1

    class SelectLine(Message):
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

    @on(Input.Submitted)
    def input_submitted(self, event: Input.Changed) -> None:
        event.stop()
        self.post_message(self.SelectLine())

    def post_update(self) -> None:
        update = FindDialog.Update(
            find=self.query_one("#find", Input).value,
            regex=self.query_one("#regex", Checkbox).value,
            case_sensitive=self.query_one("#case-sensitive", Checkbox).value,
        )
        self.post_message(update)

    def allow_focus_children(self) -> bool:
        return self.has_class("visible")

    def action_dismiss_find(self) -> None:
        self.post_message(FindDialog.Dismiss())

    def action_pointer_down(self) -> None:
        self.post_message(self.MovePointer(direction=+1))

    def action_pointer_up(self) -> None:
        self.post_message(self.MovePointer(direction=-1))
