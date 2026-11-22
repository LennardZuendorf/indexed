"""`indexed install opencode` — wire indexed into OpenCode, and take it out.

OpenCode differs from Claude Code and Codex in four ways that shape this module:

* **It never rewrites the configuration.** `opencode mcp list`, `debug config`
  and a full server start all read and normalise in memory; the bytes on disk are
  left alone. Nothing has to survive a round trip — and nothing repairs a hand
  edit either, so the only way to be safe is to splice *text* and validate the
  result before writing. Comments, key order, indentation and CRLF all survive.
* **Comments are legal in the file.** `opencode.json` may be JSONC (`//`,
  ``/* */`` and trailing commas are accepted by the host's parser), so the editor
  below is a small JSONC-aware scanner, not a `json.loads`/`json.dumps` round
  trip. Re-serialising would delete the user's comments, drop unknown keys the
  host tolerates, and reindent the whole file.
* **There is no hook-trust gate.** A plugin is a bare `.js` file in
  `<config>/plugins/`; the host imports it and calls `setup(ctx)` with no prompt,
  no hash and no approval marker. So this command has no trust step at all, and
  the whole install is exactly one write per artifact.
* **Code Mode is on by default.** MCP tools reach the model as
  `tools.indexed.search({...})` inside the `execute` tool, not as a flat
  `indexed_search`, so the skill payload says so (and names the flat form for
  `codemode: false` installs).

Installs four owned artifacts into the OpenCode config dir, and removes exactly
those again on ``--remove``:

==========================================  ==================================
``opencode.json`` (``mcp.indexed``)         the stdio MCP server entry
``skills/index-use/SKILL.md``               the ``index-use`` skill
``plugins/indexed-nudge.js``                the context nudge plugin
``indexed-install.json``                    what was installed, by version
==========================================  ==================================

The server goes under the **flat** key ``mcp.indexed`` — not
``mcp.servers.indexed``. This build accepts the flat form and normalises it into
``mcp.servers`` in memory, and public opencode 1.x only understands the flat
one, so a single file serves both.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, NoReturn, Optional, Sequence

import typer

from indexed.cli import install as base
from indexed.cli.utils.components import (
    get_dim_style,
    get_heading_style,
    get_label_style,
    print_error,
    print_success,
    print_warning,
)
from indexed.cli.utils.console import console, render_user_text
from indexed.utils.version import installed_version

# Must stay "indexed": the skill text and the plugin's nudge both name
# `tools.indexed.search`, and the flat fallback is named after the server.
SERVER_NAME = "indexed"
SKILL_NAME = "index-use"
SKILL_PAYLOAD = "installers/opencode/index-use.SKILL.md"
PLUGIN_NAME = "indexed-nudge.js"
PLUGIN_PAYLOAD = f"installers/opencode/{PLUGIN_NAME}"
PLUGIN_ID = "indexed-nudge"
INSTALL_SCHEMA = 1
MANIFEST_NAME = "indexed-install.json"
# Replaced with the collections root at install time, so `--home` reaches the
# plugin as well as the MCP server entry.
COLLECTIONS_PLACEHOLDER = "{{COLLECTIONS_ROOT}}"
# First line of the plugin, and half of what makes `--remove` recognise it. The
# match is the stable prefix, not the version: a v2 payload must still let
# `--remove` delete a v1 plugin the host is auto-loading.
PLUGIN_MARKER = "indexed-install-hook"
# The skill's own ownership mark. Unknown `metadata` sub-keys are tolerated by
# the host's frontmatter parser, so this cannot make the skill unreadable.
SKILL_MARKER_KEY = "indexed/managed"
SKILL_MARKER_VALUE = "1"
# The flat placement this command writes, and the container it lives in. Both
# are recorded separately: `--remove` may prune `mcp` only if this install
# created it (see `_plan_removal`).
SERVER_KEY = f"mcp.{SERVER_NAME}"
CONTAINER_KEY = "mcp"

app = typer.Typer(help="Install indexed integrations for coding agents")


# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
def opencode_config_dir() -> Path:
    """The OpenCode config dir: ``$OPENCODE_CONFIG_DIR``, else the XDG one.

    The host resolves exactly these two in this order (`opencode debug paths`
    prints ``config`` from them), so an installer that guessed ``~/.config`` would
    write a file the host never reads.
    """
    override = os.environ.get("OPENCODE_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    xdg_root = os.environ.get("XDG_CONFIG_HOME")
    root = Path(xdg_root).expanduser() if xdg_root else Path.home() / ".config"
    return root / "opencode"


def opencode_config_path() -> Path:
    """`opencode.json`, or `opencode.jsonc` when that is the one that exists.

    Both names are read by the host. When both exist this edits `opencode.json`
    (the name the host's own `mcp add` writes) rather than adding a second
    document; with only `.jsonc` present it edits that. With neither present it
    creates `opencode.json`.
    """
    directory = opencode_config_dir()
    config = directory / "opencode.json"
    if config.is_file():
        return config
    jsonc = directory / "opencode.jsonc"
    if jsonc.is_file():
        return jsonc
    return config


def opencode_skill_path() -> Path:
    """Where the host reads a global skill (`<config>/skills/<id>/SKILL.md`).

    The skill *id* is the directory name, so the directory is what must stay
    ``index-use``; the frontmatter `name` only changes the display name.
    """
    return opencode_config_dir() / "skills" / SKILL_NAME / "SKILL.md"


def opencode_plugin_path() -> Path:
    """The nudge plugin. A bare `.js` here auto-loads: no config entry, no trust."""
    return opencode_config_dir() / "plugins" / PLUGIN_NAME


def opencode_manifest_path() -> Path:
    """Record of what this installer owns in the OpenCode config dir."""
    return opencode_config_dir() / MANIFEST_NAME


# --------------------------------------------------------------------------- #
# Payloads (shipped in the wheel, readable from a source checkout)
# --------------------------------------------------------------------------- #
def read_skill_text() -> str:
    """The `index-use` skill payload, written for Code Mode tool naming."""
    return base.read_payload(SKILL_PAYLOAD)


def installed_plugin_text(home_override: Optional[Path]) -> str:
    """The plugin as installed, with its collections root baked in.

    The root goes in as a *JSON string literal* (`json.dumps`), which is also a
    valid JS string literal: a `--home` containing `$`, a backtick or a quote
    stays a literal path instead of something the plugin would evaluate.
    """
    root = base.collections_root(home_override)
    return base.read_payload(PLUGIN_PAYLOAD).replace(
        COLLECTIONS_PLACEHOLDER, json.dumps(str(root))
    )


def read_text_raw(path: Path) -> str:
    """Read a file without newline translation, so CRLF stays CRLF."""
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            return handle.read()
    except UnicodeDecodeError as exc:
        raise OpenCodeConfigError(
            path, "could not be read", "the file is not valid UTF-8"
        ) from exc


def write_text_raw_atomic(path: Path, text: str) -> None:
    """`base.write_text_atomic`, but the bytes written are exactly `text`.

    Text mode would translate every `\\n` to the platform's newline, turning a
    CRLF config into CRCRLF on Windows; the contract here is that the user's file
    comes back unchanged.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        os.replace(tmp_name, path)
    except BaseException:
        with contextlib.suppress(OSError):
            Path(tmp_name).unlink()
        raise


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #
class OpenCodeConfigError(ValueError):
    """An unreadable config, with the path and the reason kept apart.

    One flat message (``"<path> is not valid JSON: <reason>"``) is rendered as a
    single paragraph, so a long path folds the parser's reason across lines and
    the actionable part stops being greppable. Carrying the parts separately lets
    the command print each on its own unbroken line.
    """

    def __init__(self, path: Path, headline: str, reason: str) -> None:
        super().__init__(f"{path} {headline}: {reason}")
        self.path = path
        self.headline = headline
        self.reason = reason


class _JsoncSyntaxError(ValueError):
    """A structural problem in a JSONC document, with the offset it was seen at."""

    def __init__(self, message: str, position: int) -> None:
        super().__init__(f"{message} (at character {position})")
        self.position = position


# --------------------------------------------------------------------------- #
# JSONC: one scan, offsets out — never a re-serialisation
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class _Member:
    """One `key: value` pair of an object, as character offsets."""

    key: str
    key_start: int  # the opening quote of the key
    key_end: int  # just past the closing quote
    value_start: int  # first byte of the value (tight: no whitespace)
    value_end: int  # just past the value's last byte
    comma_before: Optional[int]  # separator from the previous member, if any


@dataclass(frozen=True)
class _Object:
    """One object in the document, as offsets plus its member list."""

    path: tuple[str, ...]
    start: int  # the "{"
    end: int  # just past the "}"
    members: tuple[_Member, ...]
    trailing_comma: Optional[int]  # a comma with nothing after it, if present
    open_line_indent: str  # indentation of the line the "{" sits on
    child_indent: Optional[str]  # indentation of the first member's line


@dataclass(frozen=True)
class JsoncDocument:
    """What one scan found: objects by member path, plus a trivia count.

    Paths are tuples of keys (`("mcp", "indexed")`); array elements contribute
    `"[n]"` so two objects with the same keys in different elements cannot
    collide. `comments` is how a caller tells "the user still has notes in this
    file" from "this file is only our leftovers".
    """

    objects: dict[tuple[str, ...], _Object]
    comments: int


_NUMBER = re.compile(r"-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?")
_WORD = re.compile(r"(?:true|false|null)(?![A-Za-z0-9_])")


class _JsoncScanner:
    """Recursive-descent walk that records offsets and never decodes values.

    It has to understand strings (with escapes) and both comment forms, or a `}`
    inside a comment or a `//` inside a URL would move every offset after it. It
    accepts trailing commas and single-line objects because the host's parser
    does; anything else is a syntax error, which the caller turns into a refusal
    before a single byte is written.
    """

    def __init__(self, text: str) -> None:
        self.text = text
        self.index = 0
        self.comments = 0
        self.objects: dict[tuple[str, ...], _Object] = {}

    # -- primitives ------------------------------------------------------- #
    def _peek(self) -> str:
        return self.text[self.index] if self.index < len(self.text) else ""

    def _fail(self, message: str) -> NoReturn:
        raise _JsoncSyntaxError(message, self.index)

    def _skip_trivia(self) -> None:
        """Skip whitespace and comments. Comments are counted, not kept."""
        while self.index < len(self.text):
            char = self.text[self.index]
            if char in " \t\r\n":
                self.index += 1
                continue
            if self.text.startswith("//", self.index):
                newline = self.text.find("\n", self.index)
                self.comments += 1
                self.index = len(self.text) if newline == -1 else newline
                continue
            if self.text.startswith("/*", self.index):
                close = self.text.find("*/", self.index + 2)
                if close == -1:
                    self._fail("unterminated /* comment")
                self.comments += 1
                self.index = close + 2
                continue
            return

    def _line_indent(self, index: int) -> str:
        """The leading whitespace of the line `index` sits on."""
        line_start = self.text.rfind("\n", 0, index) + 1
        prefix = self.text[line_start:index]
        return prefix[: len(prefix) - len(prefix.lstrip(" \t"))]

    def _scan_string(self) -> str:
        """Decode one string literal, leaving `index` just past its quote."""
        if self._peek() != '"':
            self._fail("expected a string")
        start = self.index
        self.index += 1
        while self.index < len(self.text):
            char = self.text[self.index]
            if char == "\\":
                self.index += 2
                continue
            if char == '"':
                self.index += 1
                raw = self.text[start : self.index]
                try:
                    decoded: str = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise _JsoncSyntaxError(f"bad string: {exc.msg}", start) from exc
                return decoded
            if char in "\r\n":
                self._fail("newline inside a string")
            self.index += 1
        self._fail("unterminated string")

    def _scan_scalar(self) -> None:
        for pattern in (_NUMBER, _WORD):
            match = pattern.match(self.text, self.index)
            if match is not None:
                self.index = match.end()
                return
        self._fail(f"unexpected {self._peek()!r}")

    # -- values ----------------------------------------------------------- #
    def _scan_value(self, path: tuple[str, ...]) -> None:
        char = self._peek()
        if char == "{":
            self._scan_object(path)
        elif char == "[":
            self._scan_array(path)
        elif char == '"':
            self._scan_string()
        else:
            self._scan_scalar()

    def _scan_array(self, path: tuple[str, ...]) -> None:
        self.index += 1  # "["
        position = 0
        self._skip_trivia()
        if self._peek() == "]":
            self.index += 1
            return
        while True:
            self._skip_trivia()
            self._scan_value(path + (f"[{position}]",))
            position += 1
            self._skip_trivia()
            char = self._peek()
            if char == ",":
                # A trailing comma before "]" is legal JSONC.
                self.index += 1
                self._skip_trivia()
                if self._peek() == "]":
                    self.index += 1
                    return
                continue
            if char == "]":
                self.index += 1
                return
            self._fail("expected ',' or ']' in an array")

    def _scan_object(self, path: tuple[str, ...]) -> None:
        start = self.index
        self.index += 1  # "{"
        members: list[_Member] = []
        trailing_comma: Optional[int] = None
        comma_before: Optional[int] = None
        child_indent: Optional[str] = None
        self._skip_trivia()
        if self._peek() == "}":
            self.index += 1
            self._record(path, start, members, trailing_comma, child_indent)
            return
        while True:
            trailing_comma = None
            self._skip_trivia()
            key_start = self.index
            key = self._scan_string()
            key_end = self.index
            if any(existing.key == key for existing in members):
                # Which member is "ours" would be a guess (and `json.loads`
                # takes the last one), so refuse any duplicate key, whatever
                # its value type. A duplicate object path is caught in _record.
                self._fail("duplicate key " + ".".join(path + (key,)))
            self._skip_trivia()
            if self._peek() != ":":
                self._fail("expected ':' after an object key")
            self.index += 1
            self._skip_trivia()
            if child_indent is None:
                child_indent = self._line_indent(key_start)
            value_start = self.index
            self._scan_value(path + (key,))
            members.append(
                _Member(key, key_start, key_end, value_start, self.index, comma_before)
            )
            self._skip_trivia()
            char = self._peek()
            if char == ",":
                comma_before = self.index
                trailing_comma = self.index
                self.index += 1
                self._skip_trivia()
                if self._peek() == "}":
                    # A trailing comma before "}" is legal JSONC.
                    self.index += 1
                    break
                continue
            if char == "}":
                self.index += 1
                break
            self._fail("expected ',' or '}' in an object")
        self._record(path, start, members, trailing_comma, child_indent)

    def _record(
        self,
        path: tuple[str, ...],
        start: int,
        members: list[_Member],
        trailing_comma: Optional[int],
        child_indent: Optional[str],
    ) -> None:
        if path in self.objects:
            # Two members with the same path means the file is ambiguous: which
            # one is "ours" would be a guess, so refuse instead of picking.
            self._fail("duplicate key " + ".".join(path))
        self.objects[path] = _Object(
            path=path,
            start=start,
            end=self.index,
            members=tuple(members),
            trailing_comma=trailing_comma,
            open_line_indent=self._line_indent(start),
            child_indent=child_indent,
        )

    # -- entry point ------------------------------------------------------ #
    def scan_document(self) -> None:
        self._skip_trivia()
        if self.index >= len(self.text):
            self._fail("the document holds no JSON value")
        self._scan_value(())
        self._skip_trivia()
        if self.index != len(self.text):
            self._fail("unexpected content after the top-level value")


def scan_jsonc(text: str) -> JsoncDocument:
    """Walk JSONC text once, recording every object and its member offsets.

    Structural only: no value is decoded here. Reading and writing are kept
    apart on purpose — the edit path must never round-trip a document through a
    serialiser, so anything that needs the *data* goes through `read_document`.
    """
    scanner = _JsoncScanner(text)
    scanner.scan_document()
    return JsoncDocument(scanner.objects, scanner.comments)


def strip_jsonc(text: str) -> str:
    """`text` with comments and trailing commas removed, strings untouched.

    Used only to hand the document to `json.loads` (reading values, and the final
    "is the result still JSON" check). The text written to disk is always the
    spliced original, never this.
    """
    out: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char == '"':
            scanner = _JsoncScanner(text)
            scanner.index = index
            scanner._scan_string()
            out.append(text[index : scanner.index])
            index = scanner.index
            continue
        if text.startswith("//", index):
            newline = text.find("\n", index)
            out.append(" ")
            index = length if newline == -1 else newline
            continue
        if text.startswith("/*", index):
            close = text.find("*/", index + 2)
            out.append(" ")
            index = length if close == -1 else close + 2
            continue
        if char == ",":
            # Drop a comma that is followed by "}" or "]": the host accepts it,
            # `json.loads` does not.
            look = index + 1
            while look < length:
                if text[look] in " \t\r\n":
                    look += 1
                elif text.startswith("//", look):
                    newline = text.find("\n", look)
                    look = length if newline == -1 else newline
                elif text.startswith("/*", look):
                    close = text.find("*/", look + 2)
                    look = length if close == -1 else close + 2
                else:
                    break
            if look < length and text[look] in "}]":
                index += 1
                continue
        out.append(char)
        index += 1
    return "".join(out)


def read_document(path: Path) -> dict[str, Any]:
    """Parse an existing config for reading, or return an empty document."""
    if not path.is_file():
        return {}
    try:
        text = read_text_raw(path)
    except OSError as exc:
        raise OpenCodeConfigError(path, "could not be read", str(exc)) from exc
    if not text.strip():
        return {}
    try:
        data = json.loads(strip_jsonc(text))
    except json.JSONDecodeError as exc:
        raise OpenCodeConfigError(
            path,
            "is not valid JSON",
            f"{exc.msg} (line {exc.lineno}, column {exc.colno})",
        ) from exc
    except _JsoncSyntaxError as exc:
        raise OpenCodeConfigError(path, "is not valid JSON", str(exc)) from exc
    if not isinstance(data, dict):
        raise OpenCodeConfigError(
            path,
            "does not hold a JSON object",
            f"the top-level value is a {type(data).__name__}",
        )
    return data


# --------------------------------------------------------------------------- #
# JSONC: layout helpers
# --------------------------------------------------------------------------- #
def line_ending(text: str) -> str:
    """The newline style the file already uses (`\\r\\n` files stay CRLF)."""
    return "\r\n" if "\r\n" in text else "\n"


def indent_unit(text: str) -> str:
    """The indent step the file already uses (two spaces unless it says otherwise).

    The smallest positive indentation is the step: a four-space file answers four,
    and a file with deep continuations still answers two as long as any line is
    indented by two. A tab-indented file answers a tab rather than a guess.
    """
    widths: set[int] = set()
    tabbed = False
    for line in text.splitlines():
        stripped = line.lstrip(" \t")
        if not stripped or stripped == line:
            continue  # a blank line, or a top-level line: nothing to learn
        indent = line[: len(line) - len(stripped)]
        if indent.startswith("\t"):
            tabbed = True
            continue
        widths.add(len(indent))
    if tabbed:
        return "\t"
    return " " * min(widths) if widths else "  "


def render_value(value: Any, indent: str, unit: str, eol: str) -> str:
    """One JSON value, laid out with the file's own indent unit and newlines.

    `indent` is the indentation of the line the value starts on, so an object
    closes at the same column its key sits at:
    ``"indexed": {`` … ``    }``. Lists of scalars (our `command`) stay on one
    line, which is what the host's own `mcp add` writes.
    """
    if isinstance(value, dict):
        if not value:
            return "{}"
        inner = indent + unit
        body = ("," + eol).join(
            f"{inner}{json.dumps(key, ensure_ascii=False)}: "
            f"{render_value(item, inner, unit, eol)}"
            for key, item in value.items()
        )
        return "{" + eol + body + eol + indent + "}"
    if isinstance(value, list):
        if all(not isinstance(item, (dict, list)) for item in value):
            return json.dumps(value, ensure_ascii=False)
        inner = indent + unit
        body = ("," + eol).join(
            f"{inner}{render_value(item, inner, unit, eol)}" for item in value
        )
        return "[" + eol + body + eol + indent + "]"
    return json.dumps(value, ensure_ascii=False)


def _find_member(obj: _Object, key: str) -> Optional[_Member]:
    """The last member called `key` in `obj`, or None."""
    for member in reversed(obj.members):
        if member.key == key:
            return member
    return None


def _is_multiline(text: str, obj: _Object) -> bool:
    """True when the object's members are spread over more than one line."""
    return "\n" in text[obj.start : obj.end]


def insert_member(
    text: str,
    document: JsoncDocument,
    object_path: tuple[str, ...],
    key: str,
    value: Any,
) -> str:
    """`text` with `key: value` added to the object at `object_path`.

    Three shapes, each chosen to leave every other byte where it was:

    * a multi-line object gains a line at the object's own child indent, with a
      comma after its last member (or after an existing trailing comma);
    * a single-line object gains an inline member, so it stays one line;
    * an empty object is opened up, one member per line, because that is the
      shape every file the host itself writes has.
    """
    obj = document.objects[object_path]
    unit = indent_unit(text)
    eol = line_ending(text)
    indent = (
        obj.child_indent
        if obj.child_indent is not None
        else obj.open_line_indent + unit
    )
    rendered = f"{json.dumps(key, ensure_ascii=False)}: {render_value(value, indent, unit, eol)}"
    if not obj.members:
        body = text[obj.start + 1 : obj.end - 1]
        if body.strip():
            # The body holds more than whitespace — a commented-out server, a
            # note. Appending after it keeps the user's text; rebuilding the
            # body as `{`+member+`}` would silently delete it.
            return (
                text[: obj.end - 1]
                + eol
                + indent
                + rendered
                + eol
                + obj.open_line_indent
                + text[obj.end - 1 :]
            )
        return (
            text[: obj.start + 1]
            + eol
            + indent
            + rendered
            + eol
            + obj.open_line_indent
            + text[obj.end - 1 :]
        )
    last = obj.members[-1]
    if not _is_multiline(text, obj):
        addition = (
            ", "
            + json.dumps(key, ensure_ascii=False)
            + ": "
            + json.dumps(value, ensure_ascii=False)
        )
        return text[: last.value_end] + addition + text[last.value_end :]
    if obj.trailing_comma is not None:
        # Insert after the comma and keep a real comma after our member, so the
        # user's trailing comma survives removal as a separator rather than
        # being consumed by the insert.
        at = obj.trailing_comma + 1
        addition = eol + indent + rendered + ","
    else:
        at = last.value_end
        addition = "," + eol + indent + rendered
    return text[:at] + addition + text[at:]


def replace_member_value(
    text: str,
    document: JsoncDocument,
    object_path: tuple[str, ...],
    key: str,
    value: Any,
) -> str:
    """`text` with the value of `object_path.key` replaced, key and colon kept.

    The new value keeps the layout the old one had: a compact entry in a
    single-line document stays compact (so a re-run is a byte-for-byte no-op),
    and an entry spread over several lines is rewritten at the same indent.
    """
    member = _find_member(document.objects[object_path], key)
    if member is None:  # pragma: no cover - caller checked
        return text
    single_line = "\n" not in text[member.value_start : member.value_end]
    if single_line and isinstance(value, (dict, list)):
        rendered = json.dumps(value, ensure_ascii=False)
    else:
        rendered = render_value(
            value,
            _line_indent_at(text, member.key_start),
            indent_unit(text),
            line_ending(text),
        )
    return text[: member.value_start] + rendered + text[member.value_end :]


def delete_member(
    text: str, document: JsoncDocument, object_path: tuple[str, ...], key: str
) -> str:
    """`text` without `object_path.key`, and exactly one adjacent comma.

    Deleting a middle member takes the comma and line break *after* it, so the
    next member slides into its place; deleting the last takes the separator
    before it. Both directions put back exactly the bytes an `insert_member` of
    the same member added, which is what makes `--remove` byte-exact.
    """
    obj = document.objects[object_path]
    member = _find_member(obj, key)
    if member is None:  # pragma: no cover - caller checked
        return text
    if len(obj.members) == 1:
        # Collapse to `{}` only when nothing a human wrote is left inside: a
        # comment in the body is the user's content, and deleting it would also
        # let `--remove` conclude the file is empty and delete the whole file.
        end = (
            obj.trailing_comma + 1
            if obj.trailing_comma is not None
            else member.value_end
        )
        remaining = text[obj.start + 1 : member.key_start] + text[end : obj.end - 1]
        if not remaining.strip():
            return text[: obj.start + 1] + text[obj.end - 1 :]
        return text[: member.key_start] + text[end:]
    position = obj.members.index(member)
    if position < len(obj.members) - 1:
        # Remove our member and the comma that followed it, not the run up to
        # the next key: anything a human wrote in between (a comment, a blank
        # line) belongs to the next member and must survive.
        limit = obj.members[position + 1].key_start
        comma = text.find(",", member.value_end, limit)
        end = comma + 1 if comma != -1 else limit
        return text[: member.key_start] + text[end:]
    if obj.trailing_comma is not None and member.comma_before is not None:
        # Our member was appended after an existing trailing comma and carries
        # its own: keep the user's comma and drop only what the insert added.
        return text[: member.comma_before + 1] + text[obj.trailing_comma + 1 :]
    if member.comma_before is None:  # pragma: no cover - unreachable when valid
        return text[: member.key_start] + text[member.value_end :]
    return text[: member.comma_before] + text[member.value_end :]


def _line_indent_at(text: str, index: int) -> str:
    """The leading whitespace of the line `index` sits on."""
    line_start = text.rfind("\n", 0, index) + 1
    prefix = text[line_start:index]
    return prefix[: len(prefix) - len(prefix.lstrip(" \t"))]


# --------------------------------------------------------------------------- #
# JSONC: the guard rails
# --------------------------------------------------------------------------- #
def _member_paths(document: JsoncDocument) -> set[tuple[str, ...]]:
    """Every member path in the document (keys, and array indices)."""
    paths: set[tuple[str, ...]] = set()
    for obj in document.objects.values():
        for member in obj.members:
            paths.add(obj.path + (member.key,))
    return paths


def _within(path: tuple[str, ...], allowed: tuple[str, ...]) -> bool:
    return path == allowed or path[: len(allowed)] == allowed


def _scan_or_raise(text: str, path: Path) -> JsoncDocument:
    """`scan_jsonc`, with the scanner's complaint shaped like a config error."""
    try:
        document = scan_jsonc(text)
    except _JsoncSyntaxError as exc:
        raise OpenCodeConfigError(path, "is not valid JSON", str(exc)) from exc
    if () not in document.objects:
        raise OpenCodeConfigError(
            path,
            "does not hold a JSON object",
            "the top-level value is not an object",
        )
    return document


def guard_edit(
    before: str, after: str, allowed: Sequence[tuple[str, ...]], path: Path
) -> None:
    """Refuse an edit that would drop a member the user had, or leave bad JSON.

    The editor splices at computed offsets; this is the independent check that
    the splice did what the offsets claimed. It runs *two* checks on the result:
    the scanner's structural balance (so the file still parses as JSONC), and a
    real `json.loads` on the comment-stripped text (so the host will read it).
    Nothing is written by the caller until this returns.
    """
    if not before.strip():
        return
    original = _member_paths(_scan_or_raise(before, path))
    updated_document = _scan_or_raise(after, path)
    updated = _member_paths(updated_document)
    missing = {
        candidate
        for candidate in original - updated
        if not any(_within(candidate, item) for item in allowed)
    }
    if missing:
        raise OpenCodeConfigError(
            path,
            "could not be edited safely",
            "the edit would drop "
            + ", ".join(".".join(item) for item in sorted(missing)),
        )
    try:
        json.loads(strip_jsonc(after))
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
        raise OpenCodeConfigError(
            path, "could not be edited safely", f"the result would not parse: {exc}"
        ) from exc


# --------------------------------------------------------------------------- #
# The server entry
# --------------------------------------------------------------------------- #
def build_server_entry(command: list[str], home: Optional[Path]) -> dict[str, Any]:
    """One local server entry in OpenCode's schema.

    `command` is an **array**: the host drops a server whose `command` is a
    string (with one line in its log, not in `mcp list`), which is exactly the
    failure an installer must not ship. `enabled: true` is implied by absence but
    is written explicitly so a future change of that default cannot switch the
    server off.
    """
    entry: dict[str, Any] = {
        "type": "local",
        "command": list(command),
        "enabled": True,
    }
    # indexed resolves collections from HOME; an override rides along in the
    # server's environment so the MCP process sees it.
    if home is not None:
        entry["environment"] = {"HOME": str(home)}
    return entry


def server_entry_is_ours(entry: object) -> bool:
    """True when a `mcp.indexed` entry is the one this installer writes.

    Matched on the command, not on the key: `--remove` leaves a user's own
    server that is called `indexed` but runs something else. The command shape
    is what identifies us, so a *different* binary whose file name is
    `indexed` (another virtualenv's launcher) does read as ours — the config
    `.bak` is the recovery path for that, and the alternative (forgetting our
    own entry after an upgrade) is worse. Both shapes `resolve_cli_command` can
    produce are recognised — the console script and the `python -m` fallback —
    so an upgrade still matches after the interpreter moves.
    """
    if not isinstance(entry, dict) or entry.get("type") != "local":
        return False
    command = entry.get("command")
    if not isinstance(command, list) or not command:
        return False
    parts = [part for part in command if isinstance(part, str)]
    if len(parts) != len(command):
        return False
    # Both separators, because a Windows path is a single POSIX file name: the
    # installer writes `indexed.exe` there and `shutil.which` returns that path.
    binary = parts[0].replace("\\", "/").rsplit("/", 1)[-1]
    if binary.lower() in {"indexed", "indexed.exe"} and parts[1:] == ["mcp", "run"]:
        return True
    return binary.lower().startswith("python") and parts[1:] == [
        "-m",
        "indexed.cli.app",
        "mcp",
        "run",
    ]


def merge_server_entry(text: str, entry: dict[str, Any], path: Path) -> str:
    """`text` with `mcp.indexed` set to `entry`, every other byte preserved.

    Creates `mcp` when it is absent, replaces our member's value when it is
    present (an upgrade), and refuses when `mcp` exists as something other than
    an object — replacing a foreign string or array there would delete whatever
    the user meant by it.
    """
    document = _scan_or_raise(text, path)
    if (CONTAINER_KEY,) in document.objects:
        parent = document.objects[(CONTAINER_KEY,)]
        if _find_member(parent, SERVER_NAME) is not None:
            updated = replace_member_value(
                text, document, (CONTAINER_KEY,), SERVER_NAME, entry
            )
        else:
            updated = insert_member(
                text, document, (CONTAINER_KEY,), SERVER_NAME, entry
            )
    elif _find_member(document.objects[()], CONTAINER_KEY) is not None:
        raise OpenCodeConfigError(
            path,
            "could not be edited safely",
            f"'{CONTAINER_KEY}' in the file is not an object",
        )
    else:
        updated = insert_member(text, document, (), CONTAINER_KEY, {SERVER_NAME: entry})
    guard_edit(text, updated, [(CONTAINER_KEY, SERVER_NAME)], path)
    return updated


def remove_server_entry(text: str, path: Path, *, prune_container: bool) -> str:
    """`text` without `mcp.indexed`, nothing else lost.

    `prune_container` is what the manifest recorded: `mcp` is only deleted when
    this install created it and it is now empty, so a user's own (even empty)
    `mcp` block stays where they put it.
    """
    document = _scan_or_raise(text, path)
    parent = document.objects.get((CONTAINER_KEY,))
    if parent is None or _find_member(parent, SERVER_NAME) is None:
        return text
    allowed: list[tuple[str, ...]] = [(CONTAINER_KEY, SERVER_NAME)]
    updated = delete_member(text, document, (CONTAINER_KEY,), SERVER_NAME)
    if prune_container:
        # Deleting inside `mcp` moved every later offset: re-scan before the
        # second edit rather than trusting the first scan's numbers.
        rescanned = _scan_or_raise(updated, path)
        container = rescanned.objects.get((CONTAINER_KEY,))
        if container is not None and not container.members:
            # Only prune an object that holds nothing but whitespace now: a
            # comment the user added inside it is their text, and deleting the
            # whole object would take it (and then the file) with it.
            body = updated[container.start + 1 : container.end - 1]
            if not body.strip():
                allowed.append((CONTAINER_KEY,))
                updated = delete_member(updated, rescanned, (), CONTAINER_KEY)
    guard_edit(text, updated, allowed, path)
    return updated


def document_is_empty(text: str) -> bool:
    """True when nothing a human wrote is left in the document.

    Comments count as content: a file whose only remaining thing is a note is
    still the user's file, and a removal that deleted it would be destructive in
    a way `--remove` must never be.
    """
    try:
        document = scan_jsonc(text)
    except _JsoncSyntaxError:
        return False
    top = document.objects.get(())
    return top is not None and not top.members and document.comments == 0


# --------------------------------------------------------------------------- #
# Ownership of the file artifacts
# --------------------------------------------------------------------------- #
def frontmatter_metadata(text: str) -> dict[str, str]:
    """Flat `metadata:` sub-keys of a SKILL.md's YAML frontmatter.

    Only the two-level shape an installer writes is understood (one `metadata:`
    line, then indented `key: value` lines). Anything else reads as "no
    metadata", which makes the file foreign — the safe direction: an
    unrecognised file is never deleted or replaced.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    values: dict[str, str] = {}
    inside = False
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line[:1] not in (" ", "\t"):
            inside = line.split(":", 1)[0].strip() == "metadata"
            continue
        if not inside:
            continue
        key, separator, value = line.strip().partition(":")
        if separator:
            values[key.strip()] = value.strip().strip("\"'")
    return values


def skill_is_ours(text: str) -> bool:
    """True when the skill file carries the marker this installer writes."""
    return frontmatter_metadata(text).get(SKILL_MARKER_KEY) == SKILL_MARKER_VALUE


def plugin_is_ours(text: str) -> bool:
    """True when the plugin file is the one this installer writes.

    Both halves are required: the header marker alone would match a file someone
    copied, and the id alone would match an unrelated plugin with our name.
    """
    return PLUGIN_MARKER in text and f'id: "{PLUGIN_ID}"' in text


def foreign_file(
    path: Path, ours: str, is_ours: Callable[[str], bool]
) -> Optional[str]:
    """Text of an existing file this installer did not write, or None.

    A hand-written file at our path belongs to the user. Unlike a foreign
    `mcp.indexed` (which `--force` may replace), this is refused even with
    `--force`: the file is at a path the host auto-loads, so silently replacing
    it would change behaviour someone else chose on purpose.
    """
    if not path.is_file():
        return None
    try:
        existing = read_text_raw(path)
    except OSError:
        return None
    except OpenCodeConfigError:
        # Not valid UTF-8: treat the file as someone else's rather than
        # overwriting something we cannot read.
        return f"{path}: not a UTF-8 text file"
    if existing == ours or is_ours(existing):
        return None
    return existing


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #
def _print_path(label: str, value: object) -> None:
    label_style = get_label_style()
    dim = get_dim_style()
    console.print(f"  [{label_style}]{label}[/{label_style}]")
    console.print(render_user_text(value, style=dim), soft_wrap=True)


def _fail_config(exc: OpenCodeConfigError) -> NoReturn:
    """Report a config refusal the way a user should see it, then exit 1.

    Every refusal — before planning or while planning — lands here, so a config
    that cannot be edited safely is a message with a file and a reason, never a
    Python traceback.
    """
    print_error(f"OpenCode config {exc.headline}")
    _print_path("File", exc.path)
    _print_path("Reason", exc.reason)
    raise typer.Exit(1) from exc


def _print_plan(changes: Sequence[base.Change]) -> None:
    """Print one line per artifact the command will touch."""
    for change in changes:
        if change.action == "unchanged":
            _print_path(change.label, f"{change.path} (already current)")
        elif change.action == "skipped":
            _print_path(change.label, f"{change.path} (not ours - left alone)")
        else:
            _print_path(change.label, f"{change.path} ({change.action})")


def _prune_emptied(path: Path) -> None:
    """Remove the directories a removal emptied, never past the config dir.

    `base.apply_changes` prunes up to the *Claude* dir; the OpenCode config dir is
    a different tree, so removal would otherwise leave `…/opencode/skills/`
    behind.
    """
    stop = opencode_config_dir()
    current = path
    while current != stop and stop in current.parents:
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent


def _apply_changes(changes: Sequence[base.Change]) -> None:
    """`base.apply_changes`, but the config keeps its exact newline bytes.

    Every other artifact is JSON or JavaScript we own outright, where text-mode
    writing is harmless; the user's config is the one file that must come back
    unchanged, CRLF and a missing final newline included. It is also the one file
    written exactly once per run — there is no trust step to make a second pass.
    """
    base.apply_changes(
        [change for change in changes if change.label not in ("Config", "Manifest")]
    )
    for change in changes:
        if change.label != "Config" or change.action in ("unchanged", "skipped"):
            continue
        if change.action == "removed":
            if change.keep_backup:
                base.backup_file(change.path)
            with contextlib.suppress(FileNotFoundError):
                change.path.unlink()
            _prune_emptied(change.path.parent)
            continue
        if change.text is None:  # pragma: no cover - defensive
            continue
        base.backup_file(change.path)
        write_text_raw_atomic(change.path, change.text)
    # The manifest goes last: if a config write failed, the record of what was
    # installed must still be there for a retry to finish the job.
    base.apply_changes([change for change in changes if change.label == "Manifest"])
    for change in changes:
        if change.action == "removed":
            _prune_emptied(change.path.parent)


# --------------------------------------------------------------------------- #
# Planning
# --------------------------------------------------------------------------- #
def _config_meta(manifest: dict[str, Any]) -> dict[str, Any]:
    """The `config` block of a manifest from an earlier install, if any."""
    recorded = manifest.get("config")
    return recorded if isinstance(recorded, dict) else {}


def _manifest(
    config_path: Path,
    *,
    created: bool,
    was_empty: bool,
    container_created: bool,
    skill_path: Path,
    plugin_path: Path,
) -> dict[str, Any]:
    return {
        "schema": INSTALL_SCHEMA,
        "package_version": installed_version(),
        "config": {
            "file": str(config_path),
            "key": SERVER_KEY,
            # What `--remove` has to know to put the file back: whether the file
            # itself was ours to delete, whether it was blank before we wrote it,
            # and whether the `mcp` block is ours to prune.
            "created": created,
            "was_empty": was_empty,
            "container_created": container_created,
        },
        "skill": str(skill_path),
        "plugin": str(plugin_path),
    }


def _plan_install(
    *,
    config_text: str,
    config_path: Path,
    manifest_path: Path,
    skill_path: Path,
    plugin_path: Path,
    skill_text: str,
    plugin_text: str,
    entry: dict[str, Any],
    previous_manifest: Optional[dict[str, Any]] = None,
) -> list[base.Change]:
    """Every artifact an install writes, with what would change about each."""
    had_file = config_path.is_file()
    # A blank file is spliced as `{}` — the host cannot read it anyway — but the
    # manifest remembers it was blank so `--remove` can put the blank back.
    base_text = config_text
    if not config_text.strip():
        base_text = "{}"
    before = _scan_or_raise(base_text, config_path)
    merged = merge_server_entry(base_text, entry, config_path)
    if not had_file and not merged.endswith(("\n", "\r")):
        # A file we create ends with a newline, like every other file we write.
        merged += line_ending(merged)

    previous = _config_meta(previous_manifest) if previous_manifest else {}
    if previous.get("file") not in (None, str(config_path)):
        # The manifest describes a different document (the user renamed or
        # replaced their config): its `created`/`was_empty` flags say nothing
        # about this file, and reusing them would let `--remove` delete it.
        previous = {}
    created = bool(previous.get("created")) or not had_file
    was_empty = bool(previous.get("was_empty")) or (
        had_file and not config_text.strip()
    )
    container_created = bool(previous.get("container_created")) or (
        (CONTAINER_KEY,) not in before.objects
    )
    manifest = _manifest(
        config_path,
        created=created,
        was_empty=was_empty,
        container_created=container_created,
        skill_path=skill_path,
        plugin_path=plugin_path,
    )
    # Blank is not the same as empty: `--remove` must put back the bytes that
    # were there, and `" \r\n"` cannot be rebuilt from a boolean.
    manifest["config"]["blank"] = config_text if was_empty else ""
    if not had_file:
        config_action = "created"
    elif merged != config_text:
        config_action = "updated"
    else:
        config_action = "unchanged"
    return [
        base.Change("Config", config_path, config_action, merged),
        base._file_change("Skill", skill_path, skill_text),
        base._file_change("Plugin", plugin_path, plugin_text),
        base._file_change("Manifest", manifest_path, base.dump_config(manifest)),
    ]


def _plan_removal(
    *,
    config_text: str,
    config_path: Path,
    document: dict[str, Any],
    manifest_path: Path,
    skill_path: Path,
    plugin_path: Path,
    manifest: dict[str, Any],
) -> list[base.Change]:
    """Every artifact a removal touches, with what would change about each."""
    changes: list[base.Change] = []
    container = document.get(CONTAINER_KEY)
    has_existing = isinstance(container, dict) and SERVER_NAME in container
    existing = (
        container[SERVER_NAME] if isinstance(container, dict) and has_existing else None
    )

    if not has_existing:
        changes.append(base.Change("Config", config_path, "unchanged"))
    elif not server_entry_is_ours(existing):
        changes.append(base.Change("Config", config_path, "skipped"))
    else:
        meta = _config_meta(manifest)
        if meta.get("file") not in (None, str(config_path)):
            # Flags recorded for another document must not authorise deleting
            # this one; without a matching manifest, only our key is removed.
            meta = {}
        remaining = remove_server_entry(
            config_text,
            config_path,
            prune_container=bool(meta.get("container_created")),
        )
        target: Optional[str] = remaining
        if document_is_empty(remaining):
            if meta.get("created"):
                # The file did not exist before the first install; a config with
                # nothing left in it is ours to take away again.
                target = None
            elif meta.get("was_empty"):
                target = meta.get("blank", "")
        if target is None:
            changes.append(base._deletion("Config", config_path))
        else:
            changes.append(
                base.Change(
                    "Config",
                    config_path,
                    "updated" if target != config_text else "unchanged",
                    target,
                )
            )

    changes.append(
        base._owned_file_removal("Skill", skill_path, skill_is_ours, keep_backup=False)
    )
    changes.append(
        base._owned_file_removal(
            "Plugin", plugin_path, plugin_is_ours, keep_backup=False
        )
    )
    changes.append(
        base._deletion("Manifest", manifest_path, keep_backup=False)
        if manifest_path.is_file()
        else base.Change("Manifest", manifest_path, "unchanged")
    )
    return changes


def _report_install(changes: Sequence[base.Change]) -> None:
    """Say what changed, in the terms a user can check against their own files."""
    by_label = {change.label: change for change in changes}

    config = by_label.get("Config")
    if config is not None and config.writes:
        console.print(
            f"[dim]Registered MCP server '{SERVER_NAME}' as {SERVER_KEY}.[/dim]"
        )
    else:
        print_warning(
            f"MCP server '{SERVER_NAME}' already registered - left unchanged."
        )

    skill = by_label.get("Skill")
    if skill is not None and skill.writes:
        console.print(f"[dim]Installed the {SKILL_NAME} skill.[/dim]")
    else:
        print_warning(f"The {SKILL_NAME} skill was already up to date.")

    plugin = by_label.get("Plugin")
    if plugin is not None and plugin.writes:
        console.print(
            "[dim]Installed the context nudge plugin "
            "(session context -> semantic search).[/dim]"
        )
    else:
        print_warning("The context nudge plugin was already up to date.")


# --------------------------------------------------------------------------- #
# The command
# --------------------------------------------------------------------------- #
@base.app.command("opencode")
def opencode(
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Print what would be written and change nothing.",
    ),
    home: Optional[str] = typer.Option(
        None,
        "--home",
        help="HOME the MCP server runs with; collections live in HOME/.indexed "
        "(default: your HOME).",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Replace an existing mcp.indexed entry that points elsewhere. Does "
        "not override a foreign skill or plugin file.",
    ),
    remove: bool = typer.Option(
        False,
        "--remove",
        help="Remove everything this installer added, leaving the rest of your "
        "configuration untouched.",
    ),
) -> None:
    """Register the indexed MCP server, skill and nudge plugin with OpenCode.

    Writes the user-scope MCP registration into the OpenCode config file
    (``mcp.indexed``), the index-use skill into ``skills/`` and a context nudge
    plugin into ``plugins/`` (comments, key order and other servers preserved).
    Safe to run again: an existing install is upgraded in place, never
    duplicated. --remove undoes exactly what was installed.

    \b
    Examples:
        indexed install opencode            # Register server + skill + plugin
        indexed install opencode --dry-run  # Show the plan first
        indexed install opencode --remove   # Undo, keep everything else
        indexed install opencode --home /data --dry-run
    """
    heading = get_heading_style()
    console.print()
    console.print(f"[{heading}]OpenCode Setup[/{heading}]")
    console.print()

    command = base.resolve_cli_command()
    # NOTE: `--home` moves the *collections*, not the config dir. The config dir
    # is the host's (`$OPENCODE_CONFIG_DIR` / XDG), so an install for another
    # HOME still lands in the OpenCode this shell would start.
    home_override = Path(home).expanduser().resolve() if home else None
    entry = build_server_entry(command, home_override)
    config_path = opencode_config_path()
    skill_path = opencode_skill_path()
    plugin_path = opencode_plugin_path()
    manifest_path = opencode_manifest_path()

    try:
        config_text = read_text_raw(config_path) if config_path.is_file() else ""
        document = read_document(config_path)
        manifest = base.read_config(manifest_path)
        skill_text = "" if remove else read_skill_text()
        plugin_text = "" if remove else installed_plugin_text(home_override)
        foreign_skill = (
            None if remove else foreign_file(skill_path, skill_text, skill_is_ours)
        )
        foreign_plugin = (
            None if remove else foreign_file(plugin_path, plugin_text, plugin_is_ours)
        )
    except OpenCodeConfigError as exc:
        _fail_config(exc)
    except base.ConfigFileError as exc:
        print_error(f"OpenCode manifest {exc.headline}")
        _print_path("File", exc.path)
        _print_path("Reason", exc.reason)
        raise typer.Exit(1) from exc
    except (FileNotFoundError, OSError) as exc:
        print_error(str(exc))
        raise typer.Exit(1) from exc

    if remove:
        try:
            changes = _plan_removal(
                config_text=config_text,
                config_path=config_path,
                document=document,
                manifest_path=manifest_path,
                skill_path=skill_path,
                plugin_path=plugin_path,
                manifest=manifest,
            )
        except OpenCodeConfigError as exc:
            _fail_config(exc)
        if not any(change.action != "unchanged" for change in changes):
            print_success("indexed is not installed in OpenCode - nothing to remove")
            return
        if dry_run:
            console.print(f"[{get_dim_style()}]Would remove:[/{get_dim_style()}]")
            _print_plan(changes)
            console.print(
                f"[{get_dim_style()}]Preview only - nothing was written "
                f"(drop --dry-run to apply).[/{get_dim_style()}]"
            )
            return
        try:
            _apply_changes(changes)
        except OSError as exc:
            print_error(f"Could not update OpenCode configuration: {exc}")
            raise typer.Exit(1) from exc
        removed = sum(1 for change in changes if change.action == "removed")
        print_success(f"Removed indexed from OpenCode - {removed} artifacts removed")
        console.print()
        _print_plan(changes)
        console.print()
        console.print(
            f"[{get_dim_style()}]Kept everything else in {config_path.name} "
            f"(a .bak copy of each written file is beside it).[/{get_dim_style()}]"
        )
        return

    container = document.get(CONTAINER_KEY)
    has_existing = isinstance(container, dict) and SERVER_NAME in container
    existing_server = (
        container[SERVER_NAME] if isinstance(container, dict) and has_existing else None
    )

    if has_existing and not server_entry_is_ours(existing_server):
        if not force:
            print_error(
                f"{config_path} already registers a {SERVER_KEY} entry "
                "that points somewhere else."
            )
            _print_path("Existing", json.dumps(existing_server))
            _print_path("Wanted", json.dumps(entry))
            print_warning(
                "Refusing to overwrite it. Re-run with --force to replace it "
                "(a .bak copy of the file is kept)."
            )
            raise typer.Exit(1)

    # v2 also reads `mcp.servers.<name>`, which this installer never writes. A
    # foreign entry there takes precedence over the flat one, so adding ours and
    # reporting success would register a server the host does not use.
    nested_servers = container.get("servers") if isinstance(container, dict) else None
    nested = (
        nested_servers.get(SERVER_NAME) if isinstance(nested_servers, dict) else None
    )
    if nested is not None and not server_entry_is_ours(nested):
        print_error(
            f"{config_path} registers mcp.servers.{SERVER_NAME}, which this "
            "installer does not own."
        )
        _print_path("Existing", json.dumps(nested))
        print_warning(
            "OpenCode reads that entry before the flat one. Remove or rename it "
            "(it is not ours to edit), then re-run."
        )
        raise typer.Exit(1)

    if foreign_skill is not None:
        # A user's own skill directory named index-use is theirs, and the host
        # auto-loads it: replacing it silently would change the agent's
        # behaviour without the user ever seeing it.
        print_error(f"{skill_path} already exists and was not written by indexed.")
        _print_path(
            "First line", foreign_skill.splitlines()[0] if foreign_skill else ""
        )
        print_warning(
            "Refusing to replace it, even with --force. Move it aside (or delete "
            "it) and re-run."
        )
        raise typer.Exit(1)

    if foreign_plugin is not None:
        print_error(f"{plugin_path} already exists and was not written by indexed.")
        _print_path(
            "First line", foreign_plugin.splitlines()[0] if foreign_plugin else ""
        )
        print_warning(
            "Refusing to replace it, even with --force. Move it aside (or delete "
            "it) and re-run."
        )
        raise typer.Exit(1)

    try:
        changes = _plan_install(
            config_text=config_text,
            config_path=config_path,
            manifest_path=manifest_path,
            skill_path=skill_path,
            plugin_path=plugin_path,
            skill_text=skill_text,
            plugin_text=plugin_text,
            entry=entry,
            previous_manifest=manifest,
        )
    except OpenCodeConfigError as exc:
        _fail_config(exc)

    if dry_run:
        console.print(f"[{get_dim_style()}]Would write:[/{get_dim_style()}]")
        _print_plan(changes)
        console.print(
            f"[{get_dim_style()}]OpenCode loads a plugin from its plugins "
            f"directory without asking, so there is nothing to approve: this "
            f"command writes the config once and never touches it again.[/{get_dim_style()}]"
        )
        console.print(
            f"[{get_dim_style()}]Preview only - nothing was written "
            f"(drop --dry-run to apply).[/{get_dim_style()}]"
        )
        return

    try:
        _apply_changes(changes)
    except OSError as exc:
        print_error(f"Could not write OpenCode configuration: {exc}")
        raise typer.Exit(1) from exc

    print_success("OpenCode is set up for indexed")
    console.print()
    _print_path("Config", config_path)
    _print_path("Server", " ".join(command))
    _print_path("Skill", skill_path)
    _print_path("Plugin", plugin_path)
    _print_path("Collections", base.collections_root(home_override))
    console.print()
    _report_install(changes)
    console.print()
    console.print(
        f"[{get_dim_style()}]Restart OpenCode; the {SKILL_NAME} skill is "
        f"advertised and the nudge plugin loads from {plugin_path.parent}."
        f"[/{get_dim_style()}]"
    )
