from dataclasses import dataclass
import re

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.suggester import Suggester
from textual.validation import Validator, ValidationResult
from textual.widget import Widget
from textual.widgets import Input, Checkbox


class Regex(Validator):
    def validate(self, value: str) -> ValidationResult:
        """Check a string is equal to its reverse."""
        try:
            re.compile(value)
        except Exception:
            return self.failure("Invalid regex")
        else:
            return self.success()


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
        Input {
            width: 1fr;
        }
        Input#find-regex {
            display: none;
        }
        Input#find-text {
            display: block;
        }
        &.-find-regex {
            Input#find-regex {
                display: block;
            }
            Input#find-text {
                display: none;
            }
        }
    }    
    """
    BINDINGS = [
        Binding("escape", "dismiss_find", "Dismiss", key_display="esc", show=False),
        Binding("down,j", "pointer_down", "Next", key_display="↓"),
        Binding("up,k", "pointer_up", "Previous", key_display="↑"),
        Binding("j", "pointer_down", "Next", key_display="↓", show=False),
        Binding("k", "pointer_up", "Previous", key_display="↑", show=False),
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
        yield Input(
            placeholder="Regex",
            id="find-regex",
            suggester=self.suggester,
            validators=[Regex()],
        )
        yield Input(
            placeholder="Find",
            id="find-text",
            suggester=self.suggester,
        )
        yield Checkbox("Case sensitive", id="case-sensitive")
        yield Checkbox("Regex", id="regex")

    def focus_input(self) -> None:
        if self.has_class("find-regex"):
            self.query_one("#find-regex").focus()
        else:
            self.query_one("#find-text").focus()

    def get_value(self) -> str:
        if self.has_class("find-regex"):
            return self.query_one("#find-regex", Input).value
        else:
            return self.query_one("#find-text", Input).value

    @on(Checkbox.Changed, "#regex")
    def on_checkbox_changed_regex(self, event: Checkbox.Changed):
        if event.value:
            self.query_one("#find-regex", Input).value = self.query_one(
                "#find-text", Input
            ).value
        else:
            self.query_one("#find-text", Input).value = self.query_one(
                "#find-regex", Input
            ).value
        self.set_class(event.value, "-find-regex")

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
            find=self.get_value(),
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
