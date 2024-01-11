from datetime import datetime
import re
from typing import Callable, NamedTuple


class Timestamp(NamedTuple):
    regex: str
    parse: Callable[[str], datetime | None]


def parse_timestamp(format: str) -> Callable[[str], datetime | None]:
    def parse(timestamp: str) -> datetime | None:
        timestamp = timestamp.rpartition("+")[0]
        try:
            return datetime.strptime(timestamp, format)
        except ValueError:
            return None

    return parse


TIMESTAMPS = [
    Timestamp(
        r"(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})\+(\d{2})",
        parse_timestamp("%Y-%m-%d %H:%M:%S"),
    )
]


def parse_extract(line: str) -> tuple[str, str, datetime | None]:
    for regex, parse_callable in TIMESTAMPS:
        match = re.search(regex, line)
        if match is None:
            continue
        remaining_line = re.sub(regex, "", line, count=1)
        try:
            return line, remaining_line.lstrip(), parse_callable(match.string)
        except Exception:
            continue
    return line, line, None


if __name__ == "__main__":
    print(parse_timestamp("%Y-%m-%d %H:%M:%S%z")("2024-01-08 13:31:48+00"))
    print(
        parse_extract(
            "2024-01-08 13:31:48+00 Wills-MacBook-Pro suhelperd[98983]: Exiting Daemon SUHelperExitCodeNoSenders"
        )
    )
