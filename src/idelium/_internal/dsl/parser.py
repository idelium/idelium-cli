"""Parser for the Idelium DSL v1 source format."""

from __future__ import annotations

import bisect
import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit


SUPPORTED_LANGUAGE_VERSION = "1.0"
SCHEMA_VERSION = "1.0"
_SCREENSHOT_NAME_RE = re.compile(r"^(?!.*\.\.)[A-Za-z0-9._-]+$")
_SENSITIVE_SELECTOR_HINTS = ("password", "passwd", "pwd", "secret", "token", "key")


@dataclass(frozen=True)
class DslDiagnostic:
    """A source-located parser diagnostic safe for command-line output."""

    code: str
    message: str
    line: int
    column: int
    remediation: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "line": self.line,
            "column": self.column,
            "remediation": self.remediation,
        }


class DslSyntaxError(ValueError):
    """Raised when DSL source cannot be converted into the canonical AST."""

    def __init__(self, diagnostic: DslDiagnostic):
        super().__init__(
            f"{diagnostic.code} at {diagnostic.line}:{diagnostic.column}: "
            f"{diagnostic.message} {diagnostic.remediation}"
        )
        self.diagnostic = diagnostic


def parse_source(source: str, *, source_name: str | None = None) -> dict[str, Any]:
    """Parse Idelium DSL v1 source and return the canonical AST document."""

    return _Parser(source, source_name=source_name).parse()


class _Parser:
    def __init__(self, source: str, *, source_name: str | None):
        self.source = source
        self.source_name = source_name
        self.index = 0
        self.line_starts = _line_starts(source)

    def parse(self) -> dict[str, Any]:
        self._skip_spacing()
        self._parse_version_declaration()
        self._require_separator(
            "Add a newline or semicolon after the DSL version declaration."
        )
        self._skip_spacing()

        tests: list[dict[str, Any]] = []
        test_names: set[str] = set()
        while not self._at_end():
            test_node = self._parse_test()
            if test_node["name"] in test_names:
                self._fail(
                    "IDELIUM_DSL_DUPLICATE_TEST",
                    test_node["span"]["start"],
                    "Duplicate test name.",
                    "Use a unique name for each test in a DSL source file.",
                )
            test_names.add(test_node["name"])
            tests.append(test_node)
            self._skip_spacing()

        if not tests:
            self._fail_at_current(
                "IDELIUM_DSL_MISSING_TEST",
                "Missing test declaration.",
                'Add at least one block such as test "Example" { open "https://example.invalid" }.',
            )

        document: dict[str, Any] = {
            "kind": "document",
            "schemaVersion": SCHEMA_VERSION,
            "languageVersion": SUPPORTED_LANGUAGE_VERSION,
            "tests": tests,
        }
        if self.source_name:
            document["sourceName"] = self.source_name
        return document

    def _parse_version_declaration(self) -> None:
        self._expect_keyword(
            "idelium",
            "IDELIUM_DSL_EXPECTED_VERSION",
            'Start the file with the version declaration: idelium 1.0.',
        )
        self._require_horizontal_spacing(
            "Add a space between idelium and the language version."
        )
        version_start = self.index
        if not self.source.startswith(SUPPORTED_LANGUAGE_VERSION, self.index):
            self._fail_at_index(
                "IDELIUM_DSL_UNSUPPORTED_VERSION",
                version_start,
                "Unsupported DSL language version.",
                "Use idelium 1.0 or migrate the source before parsing it.",
            )
        self.index += len(SUPPORTED_LANGUAGE_VERSION)
        if self._peek_word_character():
            self._fail_at_current(
                "IDELIUM_DSL_UNSUPPORTED_VERSION",
                "Unsupported DSL language version.",
                "Use idelium 1.0 or migrate the source before parsing it.",
            )

    def _parse_test(self) -> dict[str, Any]:
        start = self.index
        self._expect_keyword(
            "test",
            "IDELIUM_DSL_EXPECTED_TEST",
            'Declare a test block with test "Name" { ... }.',
        )
        self._require_horizontal_spacing("Add a space between test and the test name.")
        name = self._parse_string().value
        if not name.strip():
            self._fail_at_current(
                "IDELIUM_DSL_EMPTY_TEST_NAME",
                "Test name cannot be empty.",
                "Provide a non-empty test name.",
            )
        self._skip_spacing()
        self._expect_char(
            "{",
            "IDELIUM_DSL_EXPECTED_TEST_BODY",
            "Open the test body with {.",
        )
        self._skip_spacing()

        statements: list[dict[str, Any]] = []
        while not self._at_end() and self._current_char() != "}":
            statements.append(self._parse_statement())
            self._skip_spacing_without_newline()
            if self._current_char() == "}":
                break
            self._require_separator(
                "Separate statements with a newline or semicolon."
            )
            self._skip_spacing()

        self._expect_char(
            "}",
            "IDELIUM_DSL_EXPECTED_TEST_END",
            "Close the test body with }.",
        )
        return {
            "kind": "test",
            "name": name,
            "statements": statements,
            "span": self._span(start, self.index),
        }

    def _parse_statement(self) -> dict[str, Any]:
        start = self.index
        keyword = self._read_keyword()
        if keyword == "open":
            literal = self._parse_string_after_required_spacing(
                "Add a URL string after open."
            )
            self._validate_open_url(literal.value, literal.start)
            return {"kind": "open", "url": literal.value, "span": self._span(start)}
        if keyword == "click":
            return {
                "kind": "click",
                "locator": self._parse_locator(),
                "span": self._span(start),
            }
        if keyword == "write":
            locator = self._parse_locator()
            self._require_horizontal_spacing("Add value after the write locator.")
            self._expect_keyword(
                "value",
                "IDELIUM_DSL_EXPECTED_VALUE",
                'Use write <locator> value "text".',
            )
            literal = self._parse_string_after_required_spacing(
                "Add the text string after value."
            )
            return {
                "kind": "write",
                "locator": locator,
                "value": literal.value,
                "sensitive": self._is_sensitive(locator),
                "span": self._span(start),
            }
        if keyword == "wait":
            locator = self._parse_locator()
            self._require_horizontal_spacing("Add a wait condition after the locator.")
            condition = self._expect_one_of(
                {"present", "visible", "hidden", "clickable"},
                "IDELIUM_DSL_EXPECTED_WAIT_CONDITION",
                "Use one of: present, visible, hidden, clickable.",
            )
            node: dict[str, Any] = {
                "kind": "wait",
                "locator": locator,
                "condition": condition,
                "span": self._span(start),
            }
            if self._has_inline_required_spacing_followed_by("timeout"):
                self._require_horizontal_spacing(
                    "Add a space before the timeout keyword."
                )
                self._expect_keyword(
                    "timeout",
                    "IDELIUM_DSL_EXPECTED_TIMEOUT",
                    "Use timeout followed by a positive duration such as 10s.",
                )
                self._require_horizontal_spacing(
                    "Add a duration after the timeout keyword."
                )
                node["timeoutMilliseconds"] = self._parse_duration()
                node["span"] = self._span(start)
            return node
        if keyword == "assert":
            return self._parse_assert(start)
        if keyword == "back":
            return {"kind": "back", "span": self._span(start)}
        if keyword == "forward":
            return {"kind": "forward", "span": self._span(start)}
        if keyword == "screenshot":
            literal = self._parse_string_after_required_spacing(
                "Add a screenshot name after screenshot."
            )
            if not _SCREENSHOT_NAME_RE.fullmatch(literal.value):
                self._fail_at_index(
                    "IDELIUM_DSL_INVALID_SCREENSHOT_NAME",
                    literal.start,
                    "Invalid screenshot name.",
                    "Use only letters, numbers, dot, underscore, or dash, and do not use '..'.",
                )
            return {
                "kind": "screenshot",
                "name": literal.value,
                "span": self._span(start),
            }

        self._fail_at_index(
            "IDELIUM_DSL_UNKNOWN_STATEMENT",
            start,
            "Unknown DSL statement.",
            "Use one of: open, click, write, wait, assert, back, forward, screenshot.",
        )

    def _parse_assert(self, start: int) -> dict[str, Any]:
        self._require_horizontal_spacing("Add an assertion kind after assert.")
        assertion = self._expect_one_of(
            {"visible", "hidden", "text"},
            "IDELIUM_DSL_EXPECTED_ASSERTION",
            "Use assert visible, assert hidden, or assert text.",
        )
        if assertion in {"visible", "hidden"}:
            return {
                "kind": "assertVisibility",
                "expected": assertion,
                "locator": self._parse_locator(),
                "span": self._span(start),
            }

        locator = self._parse_locator()
        self._require_horizontal_spacing("Add a text comparison after the locator.")
        comparison = self._expect_one_of(
            {"equals", "contains"},
            "IDELIUM_DSL_EXPECTED_TEXT_COMPARISON",
            "Use equals or contains for text assertions.",
        )
        literal = self._parse_string_after_required_spacing(
            "Add the expected text string after the comparison."
        )
        return {
            "kind": "assertText",
            "locator": locator,
            "comparison": comparison,
            "expected": literal.value,
            "sensitive": self._is_sensitive(locator),
            "span": self._span(start),
        }

    def _parse_locator(self) -> dict[str, str]:
        self._require_horizontal_spacing("Add a locator after the command keyword.")
        strategy = self._expect_one_of(
            {"css", "xpath"},
            "IDELIUM_DSL_EXPECTED_LOCATOR",
            'Use a locator such as css "#submit" or xpath "//button".',
        )
        literal = self._parse_string_after_required_spacing(
            "Add a non-empty selector string after the locator strategy."
        )
        if not literal.value:
            self._fail_at_index(
                "IDELIUM_DSL_EMPTY_SELECTOR",
                literal.start,
                "Locator selector cannot be empty.",
                "Provide a non-empty CSS or XPath selector.",
            )
        return {"strategy": strategy, "value": literal.value}

    def _parse_duration(self) -> int:
        start = self.index
        while self._current_char().isdigit():
            self.index += 1
        digits = self.source[start : self.index]
        if not digits or digits.startswith("0"):
            self._fail_at_index(
                "IDELIUM_DSL_INVALID_DURATION",
                start,
                "Invalid duration.",
                "Use a positive duration such as 250ms, 10s, or 2m.",
            )
        unit_start = self.index
        if self.source.startswith("ms", self.index):
            self.index += 2
            multiplier = 1
        elif self.source.startswith("s", self.index):
            self.index += 1
            multiplier = 1000
        elif self.source.startswith("m", self.index):
            self.index += 1
            multiplier = 60000
        else:
            self._fail_at_index(
                "IDELIUM_DSL_INVALID_DURATION",
                unit_start,
                "Invalid duration unit.",
                "Use ms, s, or m after a positive integer.",
            )
        return int(digits) * multiplier

    def _read_keyword(self) -> str:
        start = self.index
        if not (self._current_char().isalpha() or self._current_char() == "_"):
            self._fail_at_current(
                "IDELIUM_DSL_EXPECTED_STATEMENT",
                "Expected a DSL statement.",
                "Start the statement with a supported lowercase keyword.",
            )
        while self._current_char().isalnum() or self._current_char() in {"_", "-"}:
            self.index += 1
        keyword = self.source[start : self.index]
        if keyword.lower() == keyword and keyword.isidentifier():
            return keyword
        self._fail_at_index(
            "IDELIUM_DSL_INVALID_KEYWORD_CASE",
            start,
            "Keywords must be lowercase.",
            "Use lowercase DSL keywords exactly as documented.",
        )

    def _expect_keyword(self, keyword: str, code: str, remediation: str) -> None:
        start = self.index
        found = self._read_keyword()
        if found != keyword:
            self._fail_at_index(code, start, f"Expected keyword '{keyword}'.", remediation)

    def _expect_one_of(self, choices: set[str], code: str, remediation: str) -> str:
        start = self.index
        found = self._read_keyword()
        if found not in choices:
            self._fail_at_index(
                code,
                start,
                f"Expected one of: {', '.join(sorted(choices))}.",
                remediation,
            )
        return found

    def _parse_string_after_required_spacing(self, remediation: str) -> _Literal:
        self._require_horizontal_spacing(remediation)
        return self._parse_string()

    def _parse_string(self) -> _Literal:
        start = self.index
        if self._current_char() != '"':
            self._fail_at_current(
                "IDELIUM_DSL_EXPECTED_STRING",
                "Expected a double-quoted string.",
                "Wrap the value in double quotes and use JSON-compatible escapes.",
            )
        self.index += 1
        while not self._at_end():
            char = self._current_char()
            if char == '"':
                self.index += 1
                raw = self.source[start : self.index]
                try:
                    return _Literal(json.loads(raw), start, self.index)
                except json.JSONDecodeError:
                    self._fail_at_index(
                        "IDELIUM_DSL_INVALID_STRING",
                        start,
                        "Invalid string literal.",
                        "Use JSON-compatible string escaping.",
                    )
            if char == "\\":
                self.index += 1
                if self._at_end():
                    break
                if self._current_char() == "u":
                    escape_start = self.index
                    self.index += 5
                    if (
                        self.index > len(self.source)
                        or not re.fullmatch(
                            r"u[0-9A-Fa-f]{4}",
                            self.source[escape_start : self.index],
                        )
                    ):
                        self._fail_at_index(
                            "IDELIUM_DSL_INVALID_STRING_ESCAPE",
                            escape_start,
                            "Invalid Unicode escape sequence.",
                            "Use four hexadecimal digits after \\u.",
                        )
                    continue
                if self._current_char() not in {'"', "\\", "/", "b", "f", "n", "r", "t"}:
                    self._fail_at_current(
                        "IDELIUM_DSL_INVALID_STRING_ESCAPE",
                        "Invalid string escape sequence.",
                        "Use a JSON-compatible escape sequence.",
                    )
                self.index += 1
                continue
            if ord(char) < 0x20:
                self._fail_at_current(
                    "IDELIUM_DSL_INVALID_STRING",
                    "Unescaped control character in string.",
                    "Escape control characters such as newlines with JSON-compatible escapes.",
                )
            self.index += 1
        self._fail_at_index(
            "IDELIUM_DSL_UNTERMINATED_STRING",
            start,
            "Unterminated string literal.",
            "Close the string with a double quote.",
        )

    def _require_horizontal_spacing(self, remediation: str) -> None:
        if self._current_char() not in {" ", "\t"}:
            self._fail_at_current(
                "IDELIUM_DSL_EXPECTED_SPACING",
                "Expected whitespace.",
                remediation,
            )
        while self._current_char() in {" ", "\t"}:
            self.index += 1

    def _require_separator(self, remediation: str) -> None:
        self._skip_spacing_without_newline()
        if self._current_char() == ";":
            self.index += 1
            return
        if self._consume_line_break():
            return
        self._fail_at_current(
            "IDELIUM_DSL_EXPECTED_SEPARATOR",
            "Expected statement separator.",
            remediation,
        )

    def _skip_spacing(self) -> None:
        while True:
            if self._current_char() in {" ", "\t"}:
                self.index += 1
            elif self._consume_line_break():
                pass
            elif self._consume_comment():
                pass
            else:
                return

    def _skip_spacing_without_newline(self) -> None:
        while True:
            if self._current_char() in {" ", "\t"}:
                self.index += 1
            elif self._current_char() == "#":
                while not self._at_end() and self._current_char() not in {"\n", "\r"}:
                    self.index += 1
            else:
                return

    def _consume_comment(self) -> bool:
        if self._current_char() != "#":
            return False
        while not self._at_end() and self._current_char() not in {"\n", "\r"}:
            self.index += 1
        self._consume_line_break()
        return True

    def _consume_line_break(self) -> bool:
        if self.source.startswith("\r\n", self.index):
            self.index += 2
            return True
        if self._current_char() == "\n":
            self.index += 1
            return True
        return False

    def _expect_char(self, char: str, code: str, remediation: str) -> None:
        if self._current_char() != char:
            self._fail_at_current(code, f"Expected '{char}'.", remediation)
        self.index += 1

    def _has_inline_required_spacing_followed_by(self, keyword: str) -> bool:
        probe = self.index
        if self.source[probe : probe + 1] not in {" ", "\t"}:
            return False
        while self.source[probe : probe + 1] in {" ", "\t"}:
            probe += 1
        return self.source.startswith(keyword, probe) and not _is_word_char(
            self.source[probe + len(keyword) : probe + len(keyword) + 1]
        )

    def _validate_open_url(self, value: str, start: int) -> None:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            self._fail_at_index(
                "IDELIUM_DSL_INVALID_URL",
                start,
                "Open command URL must be absolute HTTP or HTTPS.",
                'Use an absolute URL such as "https://example.invalid".',
            )
        if parsed.username or parsed.password:
            self._fail_at_index(
                "IDELIUM_DSL_URL_CREDENTIALS",
                start,
                "URL credentials are not allowed.",
                "Move credentials to the supported secure parameter mechanism.",
            )

    def _is_sensitive(self, locator: dict[str, str]) -> bool:
        value = locator["value"].lower()
        return any(hint in value for hint in _SENSITIVE_SELECTOR_HINTS)

    def _span(self, start: int, end: int | None = None) -> dict[str, dict[str, int]]:
        if end is None:
            end = self.index
        return {"start": self._position(start), "end": self._position(end)}

    def _position(self, index: int) -> dict[str, int]:
        line = bisect.bisect_right(self.line_starts, index)
        column = index - self.line_starts[line - 1] + 1
        return {"line": line, "column": column}

    def _fail_at_current(self, code: str, message: str, remediation: str) -> None:
        self._fail_at_index(code, self.index, message, remediation)

    def _fail_at_index(
        self, code: str, index: int, message: str, remediation: str
    ) -> None:
        self._fail(code, self._position(index), message, remediation)

    def _fail(
        self, code: str, position: dict[str, int], message: str, remediation: str
    ) -> None:
        raise DslSyntaxError(
            DslDiagnostic(
                code=code,
                message=message,
                line=position["line"],
                column=position["column"],
                remediation=remediation,
            )
        )

    def _peek_word_character(self) -> bool:
        return _is_word_char(self.current_char_or_empty())

    def _current_char(self) -> str:
        return self.current_char_or_empty()

    def current_char_or_empty(self) -> str:
        if self.index >= len(self.source):
            return ""
        return self.source[self.index]

    def _at_end(self) -> bool:
        return self.index >= len(self.source)


@dataclass(frozen=True)
class _Literal:
    value: str
    start: int
    end: int


def _line_starts(source: str) -> list[int]:
    starts = [0]
    index = 0
    while index < len(source):
        if source.startswith("\r\n", index):
            index += 2
            starts.append(index)
            continue
        if source[index] == "\n":
            index += 1
            starts.append(index)
            continue
        index += 1
    return starts


def _is_word_char(value: str) -> bool:
    return bool(value) and (value.isalnum() or value == "_")
