from datetime import datetime
import re
from typing import TypeAlias

from rich.highlighter import RegexHighlighter
from rich.text import Text

from .highlighter import LogHighlighter

ParseResult: TypeAlias = tuple[datetime | None, str, Text]


def _combine_regex(*regexes: str) -> str:
    """Combine a number of regexes in to a single regex.

    Returns:
        str: New regex with all regexes ORed together.
    """
    return "|".join(regexes)


# class LogHighlighter(RegexHighlighter):
#     base_style = "repr."
#     highlights = [
#         r"(?<![\\\w])(?P<str>b?'''.*?(?<!\\)'''|b?'.*?(?<!\\)'|b?\"\"\".*?(?<!\\)\"\"\"|b?\".*?(?<!\\)\")",
#     ]


class LogFormat:
    def parse(self, line: str, remove_timestamp: bool = True) -> ParseResult | None:
        raise NotImplementedError()


class RegexLogFormat(LogFormat):
    REGEX = re.compile(".*?")
    TIMESTAMPS = "%d/%b/%Y:%H:%M:%S %z"
    HIGHLIGHT_WORDS = ["GET", "PUT", "HEAD", "POST", "DELETE", "OPTIONS", "PATCH"]

    # STYLES = {
    #     "ip": "green",
    #     "remote_log_name": "magenta",
    #     "userid": "bold",
    #     "date": "dim",
    #     "timezone": "dim"
    #     "request_method": "bold"
    #     "path": "magenta",
    #     "request_version": "magenta",
    #     "status": "bold cyan",
    #     "length": "bold green",
    #     "referrer": "italic blue",

    # }
    highlighter = LogHighlighter()

    def parse(self, line: str, remove_timestamp: bool = True) -> ParseResult | None:
        match = self.REGEX.fullmatch(line)
        if match is None:
            return None
        groups = match.groupdict()
        timestamp = datetime.strptime(groups["date"], self.TIMESTAMP)

        if remove_timestamp:
            line = line.replace(groups["date"], "")
        # text = Text(line)
        # for group_no, match_string in enumerate(match.groups()):
        #     start, end = match.span(group_no)

        text = self.highlighter(line)

        text.highlight_words(self.HIGHLIGHT_WORDS, "bold yellow")

        return timestamp, line, text


class CommonLogFormat(RegexLogFormat):
    REGEX = re.compile(
        r'(?P<ip>.*?) (?P<remote_log_name>.*?) (?P<userid>.*?) (?P<date>\[.*?(?= ).*?\]) "(?P<request_method>.*?) (?P<path>.*?)(?P<request_version> HTTP\/.*)?" (?P<status>.*?) (?P<length>.*?) "(?P<referrer>.*?)"'
    )
    TIMESTAMP = "[%d/%b/%Y:%H:%M:%S %z]"


class CombinedLogFormat(RegexLogFormat):
    REGEX = re.compile(
        r'(?P<ip>.*?) (?P<remote_log_name>.*?) (?P<userid>.*?) \[(?P<date>.*?)(?= ) (?P<timezone>.*?)\] "(?P<request_method>.*?) (?P<path>.*?)(?P<request_version> HTTP\/.*)?" (?P<status>.*?) (?P<length>.*?) "(?P<referrer>.*?)" "(?P<user_agent>.*?)" (?P<session_id>.*?) (?P<generation_time_micro>.*?) (?P<virtual_host>.*)'
    )
    TIMESTAMP = "%d/%b/%Y:%H:%M:%S %z"


class DefaultLogFormat(LogFormat):
    highlighter = LogHighlighter()

    def parse(self, line: str, remove_timestamp: bool = True) -> ParseResult | None:
        text = self.highlighter(line)
        return None, line, text


FORMATS = [
    CommonLogFormat(),
    CombinedLogFormat(),
    DefaultLogFormat(),
]


def parse(line: str) -> ParseResult:
    for format in FORMATS:
        parse_result = format.parse(line)
        if parse_result is not None:
            return parse_result
    return None, "", Text()


if __name__ == "__main__":
    timestamp, line, text = parse(
        '38.174.114.112 - - [29/Jan/2024:13:49:22 +0000] "GET /login.php?s=Admin/login HTTP/1.1" 301 170 "-" "python-requests/2.24.0"'
    )
    from rich import print

    # print(line)

    print(text)
