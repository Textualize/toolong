from textual.app import ComposeResult
from textual.containers import Center, Vertical
from textual.reactive import reactive
from textual.widgets import Label, ProgressBar


class ScanProgressBar(Vertical):
    SCOPED_CSS = False
    DEFAULT_CSS = """
    ScanProgressBar {
        width: 100%;
        height: auto;
        margin: 2 4;
        dock: top;                    
        padding: 1 2;
        background: $primary;        
        display: block;
        text-align: center;
        display: none;
        align: center top;        
    }

    LogLines:focus ScanProgressBar.-has-content {
        display: block;
    }
    """

    message = reactive("")
    complete = reactive(0.0)

    def watch_message(self, message: str) -> None:
        self.query_one(".message", Label).update(message)
        self.set_class(bool(message), "-has-content")

    def compose(self) -> ComposeResult:
        with Center():
            yield Label(classes="message")
        with Center():
            yield ProgressBar(
                total=1.0, show_eta=False, show_percentage=False
            ).data_bind(progress=ScanProgressBar.complete)
