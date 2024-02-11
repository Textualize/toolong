from __future__ import annotations
from datetime import datetime
import re
from typing import Callable, NamedTuple


class TimestampFormat(NamedTuple):
    regex: str
    parser: Callable[[str], datetime | None]


def parse_timestamp(format: str) -> Callable[[str], datetime | None]:
    def parse(timestamp: str) -> datetime | None:
        try:
            return datetime.strptime(timestamp, format)
        except ValueError:
            return None

    return parse


# Info taken from logmerger project https://github.com/ptmcg/logmerger/blob/main/logmerger/timestamp_wrapper.py

TIMESTAMP_FORMATS = [
    TimestampFormat(
        r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}\s?(?:Z|[+-]\d{4})",
        datetime.fromisoformat,
    ),
    TimestampFormat(
        r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}",
        datetime.fromisoformat,
    ),
    TimestampFormat(
        r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}\s?(?:Z|[+-]\d{4})",
        datetime.fromisoformat,
    ),
    TimestampFormat(
        r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}",
        datetime.fromisoformat,
    ),
    TimestampFormat(
        r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\s?(?:Z|[+-]\d{4})",
        datetime.fromisoformat,
    ),
    TimestampFormat(
        r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}",
        datetime.fromisoformat,
    ),
    TimestampFormat(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2},\d{3}\s?(?:Z|[+-]\d{4})",
        datetime.fromisoformat,
    ),
    TimestampFormat(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2},\d{3}",
        datetime.fromisoformat,
    ),
    TimestampFormat(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}\s?(?:Z|[+-]\d{4}Z?)",
        datetime.fromisoformat,
    ),
    TimestampFormat(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}",
        datetime.fromisoformat,
    ),
    TimestampFormat(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\s?(?:Z|[+-]\d{4})",
        datetime.fromisoformat,
    ),
    TimestampFormat(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}",
        datetime.fromisoformat,
    ),
    TimestampFormat(
        r"[JFMASOND][a-z]{2}\s(\s|\d)\d \d{2}:\d{2}:\d{2}",
        parse_timestamp("%b %d %H:%M:%S"),
    ),
    TimestampFormat(
        r"\d{2}\/\w+\/\d{4} \d{2}:\d{2}:\d{2}",
        parse_timestamp(
            "%d/%b/%Y %H:%M:%S",
        ),
    ),
    TimestampFormat(
        r"\d{2}\/\w+\/\d{4}:\d{2}:\d{2}:\d{2} [+-]\d{4}",
        parse_timestamp("%d/%b/%Y:%H:%M:%S %z"),
    ),
    TimestampFormat(
        r"\d{10}\.\d+",
        lambda s: datetime.fromtimestamp(float(s)),
    ),
    TimestampFormat(
        r"\d{13}",
        lambda s: datetime.fromtimestamp(int(s)),
    ),
]


def parse(line: str) -> tuple[TimestampFormat | None, datetime | None]:
    """Attempt to parse a timestamp."""
    for timestamp in TIMESTAMP_FORMATS:
        regex, parse_callable = timestamp
        match = re.search(regex, line)
        if match is not None:
            try:
                return timestamp, parse_callable(match.string)
            except ValueError:
                continue
    return None, None


class TimestampScanner:
    """Scan a line for something that looks like a timestamp."""

    def __init__(self) -> None:
        self._timestamp_formats = TIMESTAMP_FORMATS.copy()

    def scan(self, line: str) -> datetime | None:
        """Scan a line.

        Args:
            line: A log line with a timestamp.

        Returns:
            A datetime or `None` if no timestamp was found.
        """
        for index, timestamp_format in enumerate(self._timestamp_formats):
            regex, parse_callable = timestamp_format
            if (match := re.search(regex, line)) is not None:
                try:
                    if (timestamp := parse_callable(match.group(0))) is None:
                        continue
                except Exception:
                    continue
                if index:
                    # Put matched format at the top so that
                    # the next line will be matched quicker
                    del self._timestamp_formats[index : index + 1]
                    self._timestamp_formats.insert(0, timestamp_format)

                return timestamp
        return None


if __name__ == "__main__":
    # print(parse_timestamp("%Y-%m-%d %H:%M:%S%z")("2024-01-08 13:31:48+00"))
    print(parse("29/Jan/2024:13:48:00 +0000"))

    scanner = TimestampScanner()

    LINES = """\
    121.137.55.45 - - [29/Jan/2024:13:45:19 +0000] "GET /blog/rootblog/feeds/posts/ HTTP/1.1" 200 107059 "-" "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
216.244.66.233 - - [29/Jan/2024:13:45:22 +0000] "GET /robots.txt HTTP/1.1" 200 132 "-" "Mozilla/5.0 (compatible; DotBot/1.2; +https://opensiteexplorer.org/dotbot; help@moz.com)"
78.82.5.250 - - [29/Jan/2024:13:45:29 +0000] "GET /blog/tech/post/real-working-hyperlinks-in-the-terminal-with-rich/ HTTP/1.1" 200 6982 "https://www.google.com/" "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
78.82.5.250 - - [29/Jan/2024:13:45:30 +0000] "GET /favicon.ico HTTP/1.1" 200 5694 "https://www.willmcgugan.com/blog/tech/post/real-working-hyperlinks-in-the-terminal-with-rich/" "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
46.244.252.112 - - [29/Jan/2024:13:46:44 +0000] "GET /blog/tech/feeds/posts/ HTTP/1.1" 200 118238 "https://www.willmcgugan.com/blog/tech/feeds/posts/" "FreshRSS/1.23.1 (Linux; https://freshrss.org)"
92.247.181.15 - - [29/Jan/2024:13:47:33 +0000] "GET /feeds/posts/ HTTP/1.1" 200 107059 "https://www.willmcgugan.com/" "Inoreader/1.0 (+http://www.inoreader.com/feed-fetcher; 26 subscribers; )"
188.27.184.30 - - [29/Jan/2024:13:47:56 +0000] "GET /feeds/posts/ HTTP/1.1" 200 107059 "-" "Mozilla/5.0 (X11; Linux x86_64; rv:115.0) Gecko/20100101 Thunderbird/115.6.1"
198.58.103.36 - - [29/Jan/2024:13:48:00 +0000] "GET /blog/tech/feeds/tag/django/ HTTP/1.1" 200 110812 "http://www.willmcgugan.com/blog/tech/feeds/tag/django/" "Superfeedr bot/2.0 http://superfeedr.com - Make your feeds realtime: get in touch - feed-id:46271263"
3.37.46.91 - - [29/Jan/2024:13:48:19 +0000] "GET /blog/rootblog/feeds/posts/ HTTP/1.1" 200 107059 "-" "node
""".splitlines()

    for line in LINES:
        print(scanner.scan(line))
