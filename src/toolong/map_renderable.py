from rich.console import Console, ConsoleOptions, RenderResult
from rich.segment import Segment
from rich.style import Style

from textual.color import Color, Gradient


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

gradient = Gradient(
    (0.0, Color.parse("transparent")),
    (0.01, Color.parse("#004578")),
    (0.8, Color.parse("#FF7043")),
    (1.0, Color.parse("#ffaa43")),
)


class MapRenderable:

    def __init__(self, data: list[int], height: int) -> None:
        self._data = data
        self._height = height

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        width = options.max_width
        height = self._height

        step = (len(self._data) / height) / 2
        data = [
            sum(self._data[round(step_no * step) : round(step_no * step + step)])
            for step_no in range(height * 2)
        ]

        max_value = max(data)
        get_color = gradient.get_color
        style_from_color = Style.from_color

        for datum1, datum2 in zip(data[::2], data[1::2]):
            value1 = (datum1 / max_value) if max_value else 0
            color1 = get_color(value1).rich_color
            value2 = (datum2 / max_value) if max_value else 0
            color2 = get_color(value2).rich_color
            yield Segment(f"{'▀' * width}\n", style_from_color(color1, color2))


if __name__ == "__main__":

    from rich import print

    map = MapRenderable([1, 4, 0, 0, 10, 4, 3, 6, 1, 0, 0, 0, 12, 10, 11, 0], 2)

    print(map)
