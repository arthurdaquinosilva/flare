"""Indents everything printed for one input under a `⎿` marker, as querky and Claude Code do."""

from __future__ import annotations

import io
import re
import threading
from typing import TextIO

_SPLIT = re.compile(r"(\r\n|\n|\r)")
_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")

FIRST = "  ⎿  "
REST = "     "


class BlockWriter(io.TextIOBase):
    """Prefixes the first visible line with `  ⎿  ` and every later one with five spaces.

    The prefix is written lazily, right before the first visible character of a line, so
    escape-only writes (clearing a line, moving the cursor) pass through untouched.
    """

    def __init__(self, real: TextIO, first: str = FIRST, rest: str = REST):
        self.real = real
        self.first = first
        self.rest = rest
        self.wrote = False  # whether any visible line has been written (the ⎿ is used up)
        self.at_line_start = True
        self.lock = threading.RLock()

    def _prefix(self) -> str:
        prefix = self.rest if self.wrote else self.first
        self.wrote = True
        return prefix

    def write(self, s: str) -> int:
        if not isinstance(s, str):
            raise TypeError(f"write() argument must be str, not {type(s).__name__}")
        with self.lock:
            out: list[str] = []
            for piece in _SPLIT.split(s):
                if not piece:
                    continue
                if piece in ("\n", "\r\n", "\r"):
                    out.append(piece)
                    self.at_line_start = True
                    continue
                if self.at_line_start and _ESCAPE.sub("", piece).strip(" "):
                    escapes = re.match(rf"(?:{_ESCAPE.pattern})*", piece).group()
                    out.append(escapes + self._prefix() + piece[len(escapes):])
                    self.at_line_start = False
                else:
                    out.append(piece)
            self.real.write("".join(out))
        return len(s)

    def flush(self) -> None:
        self.real.flush()

    def isatty(self) -> bool:
        return self.real.isatty()

    def fileno(self) -> int:
        return self.real.fileno()

    def writable(self) -> bool:
        return True

    def getvalue(self) -> str:
        return self.real.getvalue()  # type: ignore[attr-defined]

    @property
    def encoding(self) -> str:  # type: ignore[override]
        return getattr(self.real, "encoding", "utf-8")

    @property
    def buffer(self):
        return self.real.buffer
