import webbrowser

from rich.style import Style
from rich.text import Text

from textual import on
from textual.app import ComposeResult
from textual.containers import Center, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static, Markdown, Footer

TEXTUAL_LINK = "https://www.textualize.io/"
REPOSITORY_LINK = "https://github.com/Textualize/tailless"

HELP_MD = """
TooLong is a log file viewer / navigator for the terminal.

Built with [Textual](https://www.textualize.io/) by [Will McGugan](https://www.willmcgugan.com)

Repository: [https://github.com/Textualize/tailless](https://github.com/Textualize/tailless)

---

### Navigation

- `Home` / `End` Jump to start or end of file. Press `end` a second time to *tail* the current file.
- `Page Up` / `Page Down` to go to the next / previous page.
- `↑` / `↓` Move up / down a line.
- `m` / `M` Advance +1 / -1 minutes
- `h` / `H` Advance +1 / -1 hours
- `d` / `D` Advance +1 / -1 days
- `Enter` Toggle pointer mode.
- `Escape` Dismiss.

### Other keys

- `ctrl+f` Show find dialog.
- `ctrl+l` Toggle line numbers.
- `ctrl+t` Tail current file.

### Opening Files

Open files from the command line.

```bash
$ tl foo.log bar.log
```

If you specify more than one file, they will be displayed within tabs.

#### Opening compressed files

If a file is compressed with BZip or GZip, it will be uncompressed automatically:

```bash
$ tl foo.log.2.gz
```

#### Merging files

Multiple files will open in tabs. 
If you add the `--merge` switch, TooLong will merge all the log files based on their timestamps:

```bash
$ tl mysite.log* --merge
```

### Pointer mode

Pointer mode lets you navigate by line.
To enter pointer mode, press `enter` or click a line. 
When it pointer mode, the navigation keys will move this pointer rather than scroll the log file.

Press `enter` again or click the line again to expand the line in to a new panel.

Press `escape` to hide the line panel if it is visible, or to leave pointer mode if the line panel is not visible.

"""

TITLE = r"""
 _______          _                       
|__   __|        | |    Built with Textual
   | | ___   ___ | |     ___  _ __   __ _ 
   | |/ _ \ / _ \| |    / _ \| '_ \ / _` |
   | | (_) | (_) | |___| (_) | | | | (_| |
   |_|\___/ \___/|______\___/|_| |_|\__, |
                                     __/ |
   Moving at Terminal velocity      |___/ 

"""


COLORS = [
    "#881177",
    "#aa3355",
    "#cc6666",
    "#ee9944",
    "#eedd00",
    "#99dd55",
    "#44dd88",
    "#22ccbb",
    "#00bbcc",
    "#0099cc",
    "#3366bb",
    "#663399",
]


def get_title() -> Text:
    iter_colors = iter(COLORS)

    return Text.assemble(
        *(
            (
                line,
                Style(color=next(iter_colors)),
            )
            for line in TITLE.splitlines(keepends=True)
        )
    )


class HelpScreen(ModalScreen):

    CSS = """
    HelpScreen VerticalScroll {
        background: $surface;
        margin: 4 8;        
        border: heavy $accent;        
        height: 1fr;        
        .title {
            width: auto;
        }
        scrollbar-gutter: stable;
        Markdown .code_inline {
            background: $primary-darken-1;
            text-style: bold;
        }
    }    
    """

    BORDER_TITLE = "Help"

    BINDINGS = [
        ("escape", "dismiss"),
        ("a", f"go('https://www.willmcgugan.com')", "Author"),
        ("t", f"go({TEXTUAL_LINK!r})", "Textual"),
        ("r", f"go({REPOSITORY_LINK!r})", "Repository"),
    ]

    def compose(self) -> ComposeResult:

        yield Footer()
        with VerticalScroll() as vertical_scroll:
            with Center():
                yield Static(get_title(), classes="title")
            yield Markdown(HELP_MD)
        vertical_scroll.border_title = "Help"
        vertical_scroll.border_subtitle = "ESCAPE to dismiss"

    @on(Markdown.LinkClicked)
    def on_markdown_link_clicked(self, event: Markdown.LinkClicked) -> None:

        webbrowser.open(event.href)

    def action_go(self, href: str) -> None:
        webbrowser.open(href)
        self.notify(f"Opening {href}", title="Link")
