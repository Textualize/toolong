import webbrowser
from importlib.metadata import version

from rich.text import Text

from textual import on
from textual.app import ComposeResult
from textual.containers import Center, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static, Markdown, Footer

TEXTUAL_LINK = "https://www.textualize.io/"
REPOSITORY_LINK = "https://github.com/Textualize/toolong"
LOGMERGER_LINK = "https://github.com/ptmcg/logmerger"

HELP_MD = """
TooLong is a log file viewer / navigator for the terminal.

Built with [Textual](https://www.textualize.io/)

Repository: [https://github.com/Textualize/toolong](https://github.com/Textualize/toolong) Author: [Will McGugan](https://www.willmcgugan.com)

---

### Navigation

- `tab` / `shift+tab` to navigate between widgets.
- `home` / `end` Jump to start or end of file. Press `end` a second time to *tail* the current file.
- `page up` / `page down` to go to the next / previous page.
- `↑` / `↓` Move up / down a line.
- `m` / `M` Advance +1 / -1 minutes.
- `h` / `H` Advance +1 / -1 hours.
- `d` / `D` Advance +1 / -1 days.
- `enter` Toggle pointer mode.
- `escape` Dismiss.

### Other keys

- `ctrl+f` or `/` Show find dialog.
- `ctrl+l` Toggle line numbers.
- `ctrl+t` Tail current file.
- `ctrl+c` Exit the app.

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
When in pointer mode, the navigation keys will move this pointer rather than scroll the log file.

Press `enter` again or click the line a second time to expand the line in to a new panel.

Press `escape` to hide the line panel if it is visible, or to leave pointer mode if the line panel is not visible.


### Credits

Inspiration and regexes taken from [LogMerger](https://github.com/ptmcg/logmerger) by Paul McGuire.


### License

Copyright 2024 Will McGugan

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the “Software”), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

"""

TITLE = rf"""
 _______          _                       
|__   __|        | |    Built with Textual
   | | ___   ___ | |     ___  _ __   __ _ 
   | |/ _ \ / _ \| |    / _ \| '_ \ / _` |
   | | (_) | (_) | |___| (_) | | | | (_| |
   |_|\___/ \___/|______\___/|_| |_|\__, |
                                     __/ |
   Moving at Terminal velocity      |___/  v{version('toolong')}

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
    """Get the title, with a rainbow effect."""
    lines = TITLE.splitlines(keepends=True)
    return Text.assemble(*zip(lines, COLORS))


class HelpScreen(ModalScreen):
    """Simple Help screen with Markdown and a few links."""

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
        Markdown {
            margin:0 2;
        }        
        Markdown .code_inline {
            background: $primary-darken-1;
            text-style: bold;
        }
    }    
    """

    BINDINGS = [
        ("escape", "dismiss"),
        ("a", "go('https://www.willmcgugan.com')", "Author"),
        ("t", f"go({TEXTUAL_LINK!r})", "Textual"),
        ("r", f"go({REPOSITORY_LINK!r})", "Repository"),
        ("l", f"go({LOGMERGER_LINK!r})", "Logmerger"),
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
        self.action_go(event.href)

    def action_go(self, href: str) -> None:
        self.notify(f"Opening {href}", title="Link")
        webbrowser.open(href)
