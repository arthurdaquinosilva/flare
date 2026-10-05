"""Turning an exchange into rich renderables: request echo, headers, a pretty body and the footer."""

from __future__ import annotations

import json
from http import HTTPStatus

import httpx
from rich.console import Group, RenderableType
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from flare.client import Exchange
from flare.theme import Theme

# Content-type fragment → pygments lexer.
_LEXERS = (
    ("json", "json"),
    ("xml", "xml"),
    ("html", "html"),
    ("javascript", "javascript"),
    ("ecmascript", "javascript"),
    ("css", "css"),
    ("yaml", "yaml"),
    ("toml", "toml"),
    ("graphql", "graphql"),
    ("csv", "text"),
    ("markdown", "markdown"),
)
_BINARY_PREFIXES = ("image/", "audio/", "video/", "font/", "application/octet-stream", "application/pdf", "application/zip")


def format_duration(seconds: float) -> str:
    if seconds < 1e-3:
        return f"{seconds * 1e6:.0f}µs"
    if seconds < 1:
        return f"{seconds * 1e3:.0f}ms"
    if seconds < 60:
        return f"{seconds:.2f}s"
    m, s = divmod(seconds, 60)
    return f"{int(m)}m {s:.0f}s"


def format_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    for unit in ("KB", "MB", "GB"):
        n /= 1024
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}"
    return f"{n:.1f} GB"


def reason(response: httpx.Response) -> str:
    if response.reason_phrase:
        return response.reason_phrase
    try:
        return HTTPStatus(response.status_code).phrase
    except ValueError:
        return ""


def media_type(response: httpx.Response) -> str:
    return response.headers.get("content-type", "").split(";")[0].strip().lower()


def body_kind(response: httpx.Response) -> tuple[str, str]:
    """('empty'|'binary'|'text', lexer name)."""
    content = response.content
    if not content:
        return "empty", ""
    mtype = media_type(response)
    if mtype.startswith(_BINARY_PREFIXES) and not mtype.endswith(("+xml", "+json")):
        return "binary", ""
    for fragment, lexer in _LEXERS:
        if fragment in mtype:
            return "text", lexer
    try:
        text = content.decode(response.encoding or "utf-8")
    except (UnicodeDecodeError, LookupError):
        return "binary", ""
    if "\x00" in text:
        return "binary", ""
    stripped = text.lstrip()
    if stripped.startswith(("{", "[")):
        try:
            json.loads(text)
            return "text", "json"
        except ValueError:
            pass
    if stripped.startswith("<"):
        return "text", "html" if stripped[:15].lower().startswith(("<!doctype html", "<html")) else "xml"
    return "text", "text"


def pretty_body(response: httpx.Response) -> tuple[str, str]:
    """The body as display text and its lexer; JSON is re-indented."""
    kind, lexer = body_kind(response)
    if kind != "text":
        return "", lexer
    text = response.text
    if lexer == "json":
        try:
            text = json.dumps(json.loads(text), indent=2, ensure_ascii=False)
        except ValueError:
            pass
    return text.rstrip("\n"), lexer


def kind_label(response: httpx.Response) -> str:
    kind, lexer = body_kind(response)
    if kind == "empty":
        return "empty"
    if kind == "binary":
        return media_type(response) or "binary"
    return lexer if lexer != "text" else (media_type(response) or "text")


def echo(text: str, theme: Theme, alias_target: str | None = None) -> RenderableType:
    """The input line above a response: `> GET https://…`, or `> /alias  GET https://…`."""
    line = Text()
    line.append("> ", style="flare.accent.bold")
    first, _, rest = text.strip().partition(" ")
    if first.startswith("/"):
        line.append(first, style="flare.label")
        if rest:
            line.append(" " + rest, style="flare.fg")
    elif first.upper() in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"):
        line.append(first.upper(), style=f"bold {theme.method_style(first)}")
        line.append(" " + rest, style="flare.fg")
    else:
        line.append(text.strip().replace("\\\n", " ").replace("\n", " "), style="flare.fg")
    if alias_target:
        line.append("  →  ", style="flare.faint")
        line.append(alias_target, style="flare.muted")
    return line


def _header_grid(lines: list[tuple[str, str]]) -> Table:
    grid = Table.grid(padding=(0, 1))
    grid.add_column(no_wrap=True)
    grid.add_column(overflow="fold")
    for name, value in lines:
        grid.add_row(Text(name, style="flare.key"), Text(value, style="flare.muted"))
    return grid


def request_block(ex: Exchange, theme: Theme) -> list[RenderableType]:
    req = ex.request
    target = req.url.raw_path.decode("ascii", "replace")
    out: list[RenderableType] = [
        Text.assemble(("→ ", "flare.faint"), (req.method, f"bold {theme.method_style(req.method)}"), (f" {target}", "flare.fg")),
        _header_grid([(k.title() if k.islower() else k, v) for k, v in req.headers.items()]),
    ]
    if req.content:
        try:
            body = req.content.decode()
        except UnicodeDecodeError:
            body = f"<{format_size(len(req.content))} of binary data>"
        out.append(Text(body, style="flare.muted"))
    out.append(Text(""))
    return out


def response_blocks(ex: Exchange, theme: Theme, show_headers: bool, max_lines: int | None) -> list[RenderableType]:
    """Everything that goes on the rail: optional request, headers, then the body."""
    resp = ex.response
    out: list[RenderableType] = []
    if ex.spec.verbose:
        out += request_block(ex, theme)
    if show_headers or ex.spec.verbose:
        style = f"bold {theme.status_style(resp.status_code)}"
        out.append(Text.assemble((f"{resp.http_version} ", "flare.faint"), (f"{resp.status_code} {reason(resp)}", style)))
        out.append(_header_grid(list(resp.headers.items())))
    body = body_renderable(resp, theme, max_lines)
    if body is not None:
        if out:
            out.append(Text(""))
        out.append(body)
    return out


def body_renderable(resp: httpx.Response, theme: Theme, max_lines: int | None) -> RenderableType | None:
    kind, _ = body_kind(resp)
    if kind == "empty":
        return None
    if kind == "binary":
        return Text.assemble(
            ("binary body", "flare.muted"), (" · ", "flare.faint"), (format_size(len(resp.content)), "flare.muted"),
            (" · ", "flare.faint"), (media_type(resp) or "unknown type", "flare.muted"),
            ("  /write <file> to save it", "flare.faint"),
        )
    text, lexer = pretty_body(resp)
    lines = text.split("\n")
    hidden = 0
    if max_lines and len(lines) > max_lines:
        hidden = len(lines) - max_lines
        text = "\n".join(lines[:max_lines])
    if lexer == "text":
        body: RenderableType = Text(text, style="flare.fg")
    else:
        body = Syntax(text, lexer, theme=theme.syntax_theme, background_color="default", word_wrap=True)
    if not hidden:
        return body
    note = Text.assemble((f"… {hidden:,} more lines", "flare.muted"), ("  /body to read all of it", "flare.faint"))
    return Group(body, note)


def footer(ex: Exchange | None, theme: Theme, error: str | None = None) -> Text:
    parts: list[tuple[str, str]] = [("╰─ ", "flare.border")]
    if error or ex is None:
        return Text.assemble(*parts, ("✗ ", "flare.err.bold"), (error or "failed", "flare.err"))
    resp = ex.response
    ok = resp.status_code < 400
    color = theme.status_style(resp.status_code)
    parts += [
        ("✓ " if ok else "✗ ", color),
        (f"{resp.status_code} {reason(resp)}", f"bold {color}"),
        (" · ", "flare.faint"), (format_duration(ex.elapsed), "flare.muted"),
        (" · ", "flare.faint"), (format_size(len(resp.content)), "flare.muted"),
        (" · ", "flare.faint"), (kind_label(resp), "flare.muted"),
    ]
    if resp.history:
        n = len(resp.history)
        parts += [(" · ", "flare.faint"), (f"{n} redirect{'s' if n != 1 else ''}", "flare.muted")]
    return Text.assemble(*parts)
