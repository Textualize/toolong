from __future__ import annotations
from datetime import datetime
import json
import re
from typing_extensions import TypeAlias

from rich.highlighter import JSONHighlighter
import rich.repr
from rich.text import Text

from toolong.highlighter import LogHighlighter
from toolong import timestamps
from typing import Optional


ParseResult: TypeAlias = "tuple[Optional[datetime], str, Text]"


@rich.repr.auto
class LogFormat:
    def parse(self, line: str) -> ParseResult | None:
        raise NotImplementedError()


HTTP_GROUPS = {
    "1": "cyan",
    "2": "green",
    "3": "yellow",
    "4": "red",
    "5": "reverse red",
}


class RegexLogFormat(LogFormat):
    REGEX = re.compile(".*?")
    HIGHLIGHT_WORDS = [
        "GET",
        "POST",
        "PUT",
        "HEAD",
        "POST",
        "DELETE",
        "OPTIONS",
        "PATCH",
    ]

    highlighter = LogHighlighter()

    def parse(self, line: str) -> ParseResult | None:
        match = self.REGEX.fullmatch(line)
        if match is None:
            return None
        groups = match.groupdict()
        _, timestamp = timestamps.parse(groups["date"].strip("[]"))

        text = Text.from_ansi(line)
        if not text.spans:
            text = self.highlighter(text)
        if status := groups.get("status", None):
            text.highlight_words([f" {status} "], HTTP_GROUPS.get(status[0], "magenta"))
        text.highlight_words(self.HIGHLIGHT_WORDS, "bold yellow")

        return timestamp, line, text


class CommonLogFormat(RegexLogFormat):
    REGEX = re.compile(
        r'(?P<ip>.*?) (?P<remote_log_name>.*?) (?P<userid>.*?) (?P<date>\[.*?(?= ).*?\]) "(?P<request_method>.*?) (?P<path>.*?)(?P<request_version> HTTP\/.*)?" (?P<status>.*?) (?P<length>.*?) "(?P<referrer>.*?)"'
    )


class CombinedLogFormat(RegexLogFormat):
    REGEX = re.compile(
        r'(?P<ip>.*?) (?P<remote_log_name>.*?) (?P<userid>.*?) \[(?P<date>.*?)(?= ) (?P<timezone>.*?)\] "(?P<request_method>.*?) (?P<path>.*?)(?P<request_version> HTTP\/.*)?" (?P<status>.*?) (?P<length>.*?) "(?P<referrer>.*?)" "(?P<user_agent>.*?)" (?P<session_id>.*?) (?P<generation_time_micro>.*?) (?P<virtual_host>.*)'
    )


class DefaultLogFormat(LogFormat):
    highlighter = LogHighlighter()

    def parse(self, line: str) -> ParseResult | None:
        text = Text.from_ansi(line)
        if not text.spans:
            text = self.highlighter(text)
        return None, line, text


class JSONLogFormat(LogFormat):
    highlighter = JSONHighlighter()

    def parse(self, line: str) -> ParseResult | None:
        line = line.strip()
        if not line:
            return None
        try:
            json.loads(line)
        except Exception:
            return None
        _, timestamp = timestamps.parse(line)
        text = Text.from_ansi(line)
        if not text.spans:
            text = self.highlighter(text)
        return timestamp, line, text


FORMATS = [
    JSONLogFormat(),
    CommonLogFormat(),
    CombinedLogFormat(),
    # DefaultLogFormat(),
]

default_log_format = DefaultLogFormat()


class FormatParser:
    """Parses a log line."""

    def __init__(self) -> None:
        self._formats = FORMATS.copy()

    def parse(self, line: str) -> ParseResult:
        """Parse a line."""
        if len(line) > 10_000:
            line = line[:10_000]
        if line.strip():
            for index, format in enumerate(self._formats):
                parse_result = format.parse(line)
                if parse_result is not None:
                    if index:
                        self._formats = [*self._formats[index:], *self._formats[:index]]
                    return parse_result
        parse_result = default_log_format.parse(line)
        if parse_result is not None:
            return parse_result
        return None, "", Text()
