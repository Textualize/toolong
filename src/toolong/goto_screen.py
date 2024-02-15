from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.containers import Horizontal
from textual.widgets import Input, Label
from textual.validation import Integer

if TYPE_CHECKING:
    from toolong.log_lines import LogLines


class GotoScreen(ModalScreen):

    BINDINGS = [("escape", "dismiss")]

    DEFAULT_CSS = """

    GotoScreen {
        background: black 20%;
        align: right bottom;
        #goto {
            width: auto;
            height: auto;
            margin: 3 3;
            Label {
                margin: 1;
            }
            Input {
                width: 16;
            }
        }
    }

    """

    def __init__(self, log_lines: LogLines) -> None:
        self.log_lines = log_lines
        super().__init__()

    def compose(self) -> ComposeResult:
        log_lines = self.log_lines
        with Horizontal(id="goto"):
            yield Input(
                (
                    str(
                        log_lines.pointer_line + 1
                        if log_lines.pointer_line is not None
                        else log_lines.scroll_offset.y + 1
                    )
                ),
                placeholder="Enter line number",
                type="integer",
            )

    def on_input_changed(self, event: Input.Changed) -> None:
        try:
            line_no = int(event.value) - 1
        except Exception:
            self.log_lines.pointer_line = None
        else:
            self.log_lines.pointer_line = line_no
            self.log_lines.scroll_pointer_to_center()
