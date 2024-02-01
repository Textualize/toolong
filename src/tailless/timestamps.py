from datetime import datetime
import re
from typing import Callable, NamedTuple


class Timestamp(NamedTuple):
    regex: str
    parser: Callable[[str], datetime | None]


def parse_timestamp(format: str) -> Callable[[str], datetime | None]:
    def parse(timestamp: str) -> datetime | None:
        try:
            return datetime.strptime(timestamp, format)
        except ValueError:
            raise
            return None

    return parse


# Info taken from logmerger project https://github.com/ptmcg/logmerger/blob/main/logmerger/timestamp_wrapper.py

TIMESTAMPS = [
    Timestamp(
        r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}\s?(?:Z|[+-]\d{4})",
        datetime.fromisoformat,
    ),
    Timestamp(
        r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}",
        datetime.fromisoformat,
    ),
    Timestamp(
        r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}\s?(?:Z|[+-]\d{4})",
        datetime.fromisoformat,
    ),
    Timestamp(
        r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}",
        datetime.fromisoformat,
    ),
    Timestamp(
        r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\s?(?:Z|[+-]\d{4})",
        datetime.fromisoformat,
    ),
    Timestamp(
        r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}",
        datetime.fromisoformat,
    ),
    Timestamp(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2},\d{3}\s?(?:Z|[+-]\d{4})",
        datetime.fromisoformat,
    ),
    Timestamp(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2},\d{3}",
        datetime.fromisoformat,
    ),
    Timestamp(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}\s?(?:Z|[+-]\d{4}Z?)",
        datetime.fromisoformat,
    ),
    Timestamp(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}",
        datetime.fromisoformat,
    ),
    Timestamp(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\s?(?:Z|[+-]\d{4})",
        datetime.fromisoformat,
    ),
    Timestamp(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}",
        datetime.fromisoformat,
    ),
    Timestamp(
        r"[JFMASOND][a-z]{2}\s(\s|\d)\d \d{2}:\d{2}:\d{2}",
        parse_timestamp("%b %d %H:%M:%S"),
    ),
    Timestamp(
        r"\d{2}\/\w+\/\d{4} \d{2}:\d{2}:\d{2}",
        parse_timestamp(
            "%d/%b/%Y %H:%M:%S",
        ),
    ),
    Timestamp(
        r"\d{2}\/\w+\/\d{4}:\d{2}:\d{2}:\d{2} [+-]\d{4}",
        parse_timestamp("%d/%b/%Y:%H:%M:%S %z"),
    ),
    Timestamp(
        r"\d{10}\.\d+",
        lambda s: datetime.fromtimestamp(float(s)),
    ),
    Timestamp(
        r"\d{13}",
        lambda s: datetime.fromtimestamp(int(s)),
    ),
]


def parse(line: str) -> tuple[Timestamp | None, datetime | None]:
    """Attempt to parse a timestamp."""
    for timestamp in TIMESTAMPS:
        regex, parse_callable = timestamp
        match = re.search(regex, line)
        if match is not None:
            try:
                return timestamp, parse_callable(match.string)
            except ValueError:
                continue
    return None, None


if __name__ == "__main__":
    # print(parse_timestamp("%Y-%m-%d %H:%M:%S%z")("2024-01-08 13:31:48+00"))
    print(parse("29/Jan/2024:13:48:00 +0000"))
