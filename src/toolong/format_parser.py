from __future__ import annotations
from datetime import datetime
import json
import re
from typing_extensions import TypeAlias

from rich.highlighter import JSONHighlighter
from rich.text import Text

from toolong.highlighter import LogHighlighter
from toolong import timestamps
from typing import Optional


ParseResult: TypeAlias = "tuple[Optional[datetime], str, Text]"


class LogFormat:
    def parse(self, line: str) -> ParseResult | None:
        raise NotImplementedError()


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
            text.highlight_words(
                [f" {status} "], "bold red" if status.startswith("4") else "magenta"
            )
        text.highlight_words(self.HIGHLIGHT_WORDS, "bold yellow")

        return timestamp, line, text

class NextflowRegexLogFormatOne(LogFormat):
    REGEX = re.compile(".*?")
    LOG_LEVELS = {
        "DEBUG": ["dim white on black", ""],
        "INFO": ["bold black on green", "on #042C07"],
        "WARN": ["bold black on yellow", "on #44450E"],
        "ERROR": ["bold black on red", "on #470005"],
    }

    highlighter = LogHighlighter()

    def parse(self, line: str) -> ParseResult | None:
        match = self.REGEX.fullmatch(line)
        if match is None:
            return None

        text = Text.from_ansi(line)
        groups = match.groupdict()
#        if not text.spans:
#            text = self.highlighter(text)
        if date := groups.get("date", None):
            _, timestamp = timestamps.parse(groups["date"])
            text.highlight_words([date], "not bold magenta")
        if thread := groups.get("thread", None):
            text.highlight_words([thread], "blue")
        if log_level := groups.get("log_level", None):
            text.highlight_words([f" {log_level} "], self.LOG_LEVELS[log_level][0])
            text.stylize_before(self.LOG_LEVELS[log_level][1])
        if logger_name := groups.get("logger_name", None):
            text.highlight_words([logger_name], "cyan")
        if process_name := groups.get("process_name", None):
            text.highlight_words([process_name], "bold cyan")
        if message := groups.get("message", None):
            text.highlight_words([message], 'dim' if log_level == 'DEBUG' else '')

        return None, line, text


class NextflowRegexLogFormatTwo(LogFormat):
    REGEX = re.compile(".*?")
    highlighter = LogHighlighter()

    def parse(self, line: str) -> ParseResult | None:
        match = self.REGEX.fullmatch(line)
        if match is None:
            return None

        text = Text.from_ansi(line)
        text.stylize_before("dim")
        groups = match.groupdict()
        if process := groups.get("process", None):
            text.highlight_words([process], 'blue not dim')
        if process_name := groups.get("process_name", None):
            text.highlight_words([process_name], 'bold cyan not dim')

        return None, line, text

class NextflowRegexLogFormatThree(LogFormat):
    REGEX = re.compile(".*?")
    CHANNEL_TYPES = {
        "(value)": "green",
        "(cntrl)": "yellow",
        "(queue)": "magenta",
    }
    highlighter = LogHighlighter()

    def parse(self, line: str) -> ParseResult | None:
        match = self.REGEX.fullmatch(line)
        if match is None:
            return None

        text = Text.from_ansi(line)
        groups = match.groupdict()
        if port := groups.get("port", None):
            text.highlight_words([port], 'blue')
        if channel_type := groups.get("channel_type", None):
            text.highlight_words([channel_type], self.CHANNEL_TYPES[channel_type])
        if channel_state := groups.get("channel_state", None):
            text.highlight_words([channel_state], 'cyan' if channel_state == 'OPEN' else 'yellow')
        text.highlight_words(["; channel:"], 'dim')
        if channel_name := groups.get("channel_name", None):
            text.highlight_words([channel_name], 'cyan')

        return None, line, text

class NextflowRegexLogFormatFour(LogFormat):
    REGEX = re.compile(".*?")
    highlighter = LogHighlighter()

    def parse(self, line: str) -> ParseResult | None:
        match = self.REGEX.fullmatch(line)
        if match is None:
            return None

        text = Text.from_ansi(line)
        text.stylize_before("dim")
        groups = match.groupdict()
        text.highlight_words(["status="], 'dim')
        if status := groups.get("status", None):
            text.highlight_words([status], 'cyan not dim')

        return None, line, text


class NextflowRegexLogFormatFive(LogFormat):
    REGEX = re.compile(".*?")
    highlighter = LogHighlighter()

    def parse(self, line: str) -> ParseResult | None:
        match = self.REGEX.fullmatch(line)
        if match is None:
            return None

        text = Text.from_ansi(line)
        text.stylize_before("dim")
        groups = match.groupdict()
        if script_id := groups.get("script_id", None):
            text.highlight_words([script_id], 'blue')
        if script_path := groups.get("script_path", None):
            text.highlight_words([script_path], 'magenta')

        return None, line, text


class CommonLogFormat(RegexLogFormat):
    REGEX = re.compile(
        r'(?P<ip>.*?) (?P<remote_log_name>.*?) (?P<userid>.*?) (?P<date>\[.*?(?= ).*?\]) "(?P<request_method>.*?) (?P<path>.*?)(?P<request_version> HTTP\/.*)?" (?P<status>.*?) (?P<length>.*?) "(?P<referrer>.*?)"'
    )


class CombinedLogFormat(RegexLogFormat):
    REGEX = re.compile(
        r'(?P<ip>.*?) (?P<remote_log_name>.*?) (?P<userid>.*?) \[(?P<date>.*?)(?= ) (?P<timezone>.*?)\] "(?P<request_method>.*?) (?P<path>.*?)(?P<request_version> HTTP\/.*)?" (?P<status>.*?) (?P<length>.*?) "(?P<referrer>.*?)" "(?P<user_agent>.*?)" (?P<session_id>.*?) (?P<generation_time_micro>.*?) (?P<virtual_host>.*)'
    )


class NextflowLogFormat(NextflowRegexLogFormatOne):
    REGEX = re.compile(
        r'(?P<date>\w+-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}) (?P<thread>\[.*\]?) (?P<log_level>\w+)\s+(?P<logger_name>[\w\.]+) - (?P<message>.*?)$'
    )


class NextflowLogFormatActiveProcess(NextflowRegexLogFormatTwo):
    REGEX = re.compile(
        r'^(?P<marker>\[process\]) (?P<process>.*?)(?P<process_name>[^:]+?)?$'
    )


class NextflowLogFormatActiveProcessDetails(NextflowRegexLogFormatThree):
    REGEX = re.compile(
        r'  (?P<port>port \d+): (?P<channel_type>\((value|queue|cntrl)\)) (?P<channel_state>\S+)\s+; channel: (?P<channel_name>.*?)$'
    )


class NextflowLogFormatActiveProcessStatus(NextflowRegexLogFormatFour):
    REGEX = re.compile(
        r'^  status=(?P<status>.*?)?$'
    )


class NextflowLogFormatScriptParse(NextflowRegexLogFormatFive):
    REGEX = re.compile(
        r'^  (?P<script_id>Script_\w+:) (?P<script_path>.*?)$'
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
    # JSONLogFormat(),
    # CommonLogFormat(),
    # CombinedLogFormat(),
    NextflowLogFormat(),
    NextflowLogFormatActiveProcess(),
    NextflowLogFormatActiveProcessDetails(),
    NextflowLogFormatActiveProcessStatus(),
    NextflowLogFormatScriptParse(),
    # DefaultLogFormat(),
]


class FormatParser:
    """Parses a log line."""

    def __init__(self) -> None:
        self._formats = FORMATS.copy()

    def parse(self, line: str) -> ParseResult:
        """Parse a line."""
        if len(line) > 10_000:
            line = line[:10_000]
        for index, format in enumerate(self._formats):
            parse_result = format.parse(line)
            if parse_result is not None:
                if index:
                    del self._formats[index : index + 1]
                    self._formats.insert(0, format)
                return parse_result
        return None, line, Text.from_ansi(line)
