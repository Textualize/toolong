from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import rich.repr

from textual.app import ComposeResult
from textual import work, on
from textual.worker import get_current_worker
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from toolong.map_renderable import MapRenderable


if TYPE_CHECKING:
    from toolong.log_lines import LogLines


class Minimap(Widget):

    DEFAULT_CSS = """
    Minimap {
        width: 3;
        height: 1fr;
    }

    """

    data: reactive[list[int]] = reactive(list, always_update=True)

    @dataclass
    @rich.repr.auto
    class UpdateData(Message):
        data: list[int]

        def __rich_repr__(self) -> rich.repr.Result:
            yield self.data[:10]

    def __init__(self, log_lines: LogLines) -> None:
        self._log_lines = log_lines
        super().__init__()

    @on(UpdateData)
    def update_data(self, event: UpdateData) -> None:
        self.data = event.data

    def render(self) -> MapRenderable:
        return MapRenderable(self.data or [0, 0], self.size.height)

    def refresh_map(self, line_count: int) -> None:
        self.scan_lines(self.data.copy(), 0, line_count)

    @work(thread=True, exclusive=True)
    def scan_lines(self, data: list[int], start_line: int, end_line: int) -> None:
        worker = get_current_worker()
        line_no = start_line

        data = [0] * (((end_line - start_line) + 7) // 8)
        while line_no < end_line and not worker.is_cancelled:

            log_file, start, end = self._log_lines.index_to_span(line_no)
            line = log_file.get_line(start, end)
            *_, error = log_file.format_parser.parse(line)

            if error:
                data[line_no // 8] += 1

            line_no += 1

        if worker.is_cancelled:
            return
        self.post_message(self.UpdateData(data))
