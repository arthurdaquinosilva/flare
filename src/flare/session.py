"""One line of input at a time: a request, an alias call or a /command."""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Mapping

import httpx
from rich.console import Console, RenderableType
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from flare import render
from flare.client import Exchange, RequestError, send
from flare.config import Settings
from flare.project import AliasError, AliasStore, Project, expand, placeholders, short_path
from flare.request import ParseError, parse, split_command
from flare.theme import PALETTES, get_theme

FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

# name → (arguments, description). Aliases may not reuse these names.
COMMANDS: dict[str, tuple[str, str]] = {
    "alias": ("<name> <request>", "save a request as /name (with only a name: show it)"),
    "save": ("<name>", "save the last request as /name"),
    "aliases": ("", "list this project's aliases"),
    "unalias": ("<name>", "delete an alias"),
    "edit": ("<name>", "put an alias in the input to change it"),
    "body": ("", "read the whole last response in a pager"),
    "write": ("<file>", "write the last response body to a file"),
    "headers": ("[on|off]", "show or hide response headers"),
    "theme": ("<name>", "switch theme: " + ", ".join(PALETTES)),
    "mode": ("vi|emacs", "switch key bindings"),
    "project": ("", "where this project's aliases are kept"),
    "clear": ("", "clear the screen"),
    "help": ("", "commands, request syntax and keys"),
    "exit": ("", "leave flare"),
}


class _Verbatim(dict):
    """An environment that leaves $VARS as they are, for checking a command without its secrets."""

    def __contains__(self, key: object) -> bool:
        return True

    def __missing__(self, key: str) -> str:
        return "${" + key + "}"


def describe(command: str) -> tuple[str, str, str]:
    """(method, url, extras) for listing an alias without expanding its variables."""
    try:
        spec = parse(command, env=_Verbatim())
    except ParseError:
        return "", command, ""
    extras = []
    if spec.headers:
        n = len([h for h in spec.headers if h[0] not in ("Content-Type", "Accept")]) or len(spec.headers)
        extras.append(f"{n} header{'s' if n != 1 else ''}")
    if spec.data is not None:
        extras.append("body")
    if spec.auth:
        extras.append("auth")
    return spec.method, spec.url, ", ".join(extras)


class Session:
    def __init__(
        self,
        settings: Settings,
        project: Project,
        console: Console | None = None,
        transport: httpx.BaseTransport | None = None,
        env: Mapping[str, str] | None = None,
    ):
        self.settings = settings
        self.project = project
        self.theme = get_theme(settings.theme)
        self.console = console or Console(theme=self.theme.rich_theme, highlight=False)
        if console is not None:
            self.console.push_theme(self.theme.rich_theme)
        self.transport = transport
        self.env = os.environ if env is None else env
        self.store = AliasStore(project)
        self.last: Exchange | None = None
        self.last_command: str | None = None  # the request text behind self.last, aliases expanded
        self.last_ok: bool | None = None
        self.count = 0
        self.next_input = ""
        self.exit_requested = False
        self.raw = False  # write bare response bodies (when output is piped)
        self.on_change: Callable[[], None] = lambda: None

    # ── output helpers ────────────────────────────────────────────────────

    def print(self, *renderables: RenderableType) -> None:
        for r in renderables:
            self.console.print(r)

    def note(self, message: str, ok: bool = True, detail: str = "") -> None:
        mark = ("✓ ", "flare.ok") if ok else ("✗ ", "flare.err.bold")
        self.console.print(Text.assemble(("  ", ""), mark, (message, "flare.fg" if ok else "flare.err"), (detail, "flare.muted")))
        self.console.print()

    def _ansi(self, text: Text) -> str:
        with self.console.capture() as cap:
            self.console.print(text, end="")
        return cap.get()

    def rail(self, renderables: list[RenderableType]) -> None:
        """Print renderables indented behind a thin left rail, as ember does for cell output."""
        prefix = self._ansi(Text("│ ", style="flare.border"))
        width = max(20, self.console.width - 2)
        with self.console.capture() as cap:
            for r in renderables:
                self.console.print(r, width=width)
        lines = cap.get().rstrip("\n").split("\n")
        bare = prefix.rstrip(" ") if prefix.strip() else ""
        out = [bare] + [prefix + line if line.strip() else bare for line in lines] + [bare]
        self.console.file.write("\n".join(out) + "\n")
        self.console.file.flush()

    # ── dispatch ──────────────────────────────────────────────────────────

    def run(self, text: str) -> bool:
        """Run one input. Returns whether it succeeded."""
        stripped = text.strip()
        if not stripped:
            return True
        if not stripped.startswith("/"):
            return self.request(stripped, stripped)
        name, _, rest = stripped[1:].partition(" ")
        name, rest = name.strip(), rest.strip()
        if name in COMMANDS:
            try:
                return getattr(self, f"cmd_{name}")(rest) is not False
            except (AliasError, ValueError, KeyError, OSError) as e:
                self.note(str(e).strip("'\""), ok=False)
                return False
        command = self.store.get(name) if name else None
        if command is None:
            self.note(f"unknown command /{name}", ok=False, detail="  ·  /help lists commands, /aliases this project's aliases")
            return False
        try:
            filled = expand(command, split_command(rest))
        except (AliasError, ParseError) as e:
            self.print(render.echo(stripped, self.theme), render.footer(None, self.theme, f"/{name}: {e}"))
            self.console.print()
            return False
        return self.request(stripped, filled, alias=True)

    def request(self, shown: str, command: str, alias: bool = False) -> bool:
        self.count += 1
        if self.raw:
            return self._request_raw(command)
        target = None
        if alias:
            method, url, _ = describe(command)
            target = f"{method} {url}".strip()
        self.print(render.echo(shown, self.theme, target))
        try:
            spec = parse(command, self.env)
        except ParseError as e:
            return self._fail(str(e))
        try:
            ex = self._send_with_spinner(spec)
        except RequestError as e:
            return self._fail(str(e))
        except KeyboardInterrupt:
            return self._fail("cancelled")
        self.last, self.last_command = ex, command
        self.last_ok = ex.response.status_code < 400
        blocks = render.response_blocks(ex, self.theme, self.settings.headers, self.settings.max_lines)
        if blocks:
            self.rail(blocks)
        self.print(render.footer(ex, self.theme))
        self.console.print()
        self.on_change()
        return self.last_ok

    def _request_raw(self, command: str) -> bool:
        try:
            ex = send(parse(command, self.env), self.settings.timeout, self.transport)
        except (ParseError, RequestError) as e:
            print(f"flare: {e}", file=sys.stderr)
            return False
        self.last, self.last_command = ex, command
        out = getattr(self.console.file, "buffer", None)
        if out is not None:
            out.write(ex.response.content)
        else:
            self.console.file.write(ex.response.text)
        self.console.file.flush()
        return ex.response.status_code < 400

    def _fail(self, error: str) -> bool:
        self.last_ok = False
        self.print(render.footer(None, self.theme, error))
        self.console.print()
        self.on_change()
        return False

    def _send_with_spinner(self, spec) -> Exchange:
        if not self.console.is_terminal:
            return send(spec, self.settings.timeout, self.transport)
        stop = threading.Event()
        file = self.console.file
        host = httpx.URL(spec.url).host

        def spin() -> None:
            started, i = time.perf_counter(), 0
            while not stop.wait(0.08):
                elapsed = time.perf_counter() - started
                if elapsed < 0.15:
                    continue
                line = Text.assemble(
                    ("╰─ ", "flare.border"), (FRAMES[i % len(FRAMES)], "flare.accent"),
                    (f" {spec.method} {host} ", "flare.muted"), (render.format_duration(elapsed), "flare.faint"),
                    ("  ctrl+c to cancel", "flare.faint"),
                )
                file.write("\r\x1b[2K" + self._ansi(line))
                file.flush()
                i += 1

        thread = threading.Thread(target=spin, name="flare-spinner", daemon=True)
        thread.start()
        try:
            return send(spec, self.settings.timeout, self.transport)
        finally:
            stop.set()
            thread.join(timeout=0.5)
            file.write("\r\x1b[2K")
            file.flush()

    # ── commands ──────────────────────────────────────────────────────────

    def _need_name(self, arg: str, usage: str) -> str:
        name = arg.split()[0] if arg.split() else ""
        if not name:
            raise ValueError(f"usage: {usage}")
        return name.lstrip("/")

    def cmd_alias(self, arg: str) -> bool:
        if not arg:
            return self.cmd_aliases("")
        name, _, command = arg.partition(" ")
        name, command = name.lstrip("/"), command.strip()
        if not command:
            saved = self.store.get(name)
            if saved is None:
                raise AliasError(f"no alias /{name} in this project")
            self.print(Text.assemble(("  /", "flare.label"), (name, "flare.label")))
            self.print(Syntax("  " + saved, "bash", theme=self.theme.syntax_theme, background_color="default", word_wrap=True))
            self.console.print()
            return True
        if command.startswith("/"):
            raise AliasError("an alias can't point at another alias or command")
        try:
            parse(command, env=_Verbatim())
        except ParseError as e:
            raise AliasError(f"not saved: {e}") from None
        existed = name in self.store
        self.store.set(name, command, reserved=tuple(COMMANDS))
        method, url, _ = describe(command)
        holes = placeholders(command)
        detail = f"  →  {method} {url}" + (f"  ·  takes {' '.join('{' + h + '}' for h in holes)}" if holes else "")
        self.note(f"{'updated' if existed else 'saved'} /{name}", detail=detail)
        self.on_change()
        return True

    def cmd_save(self, arg: str) -> bool:
        name = self._need_name(arg, "/save <name>")
        if self.last_command is None:
            raise ValueError("no request yet — send one, then /save it")
        return self.cmd_alias(f"{name} {self.last_command}")

    def cmd_aliases(self, arg: str) -> bool:
        if not len(self.store):
            self.note(f"no aliases in {self.project.name} yet", detail="  ·  /alias <name> <request> or /save <name> after a request")
            return True
        table = Table.grid(padding=(0, 2))
        table.add_column(no_wrap=True)
        table.add_column(no_wrap=True)
        table.add_column(overflow="fold")
        table.add_column(no_wrap=True)
        for name, command in sorted(self.store.aliases.items()):
            method, url, extras = describe(command)
            table.add_row(
                Text("/" + name, style="flare.label"),
                Text(method, style=f"bold {self.theme.method_style(method)}"),
                Text(url, style="flare.fg"),
                Text(extras, style="flare.faint"),
            )
        self.console.print(Text.assemble(("  aliases", "flare.accent.bold"), (f"  ·  {self.project.name}", "flare.muted")))
        self.console.print()
        self.rail([table])
        return True

    def cmd_unalias(self, arg: str) -> bool:
        name = self._need_name(arg, "/unalias <name>")
        self.store.remove(name)
        self.note(f"removed /{name}")
        self.on_change()
        return True

    def cmd_edit(self, arg: str) -> bool:
        name = self._need_name(arg, "/edit <name>")
        command = self.store.get(name)
        if command is None:
            raise AliasError(f"no alias /{name} in this project")
        self.next_input = f"/alias {name} {command}"
        return True

    def _last_or_fail(self) -> Exchange:
        if self.last is None:
            raise ValueError("no response yet")
        return self.last

    def cmd_body(self, arg: str) -> bool:
        resp = self._last_or_fail().response
        body = render.body_renderable(resp, self.theme, max_lines=None)
        if body is None:
            self.note("the last response had an empty body")
            return True
        with self.console.pager(styles=True):
            self.console.print(body)
        return True

    def cmd_write(self, arg: str) -> bool:
        if not arg:
            raise ValueError("usage: /write <file>")
        resp = self._last_or_fail().response
        path = Path(os.path.expanduser(arg.strip().strip("'\"")))
        path.write_bytes(resp.content)
        self.note(f"wrote {render.format_size(len(resp.content))}", detail=f" to {short_path(path.resolve())}")
        return True

    def cmd_headers(self, arg: str) -> bool:
        self.settings.set("headers", arg if arg else not self.settings.headers)
        self.note(f"headers {'shown' if self.settings.headers else 'hidden'}")
        return True

    def cmd_theme(self, arg: str) -> bool:
        if not arg:
            self.note(f"theme {self.theme.name}", detail="  ·  available: " + ", ".join(PALETTES))
            return True
        self.settings.set("theme", arg)
        self.theme = get_theme(self.settings.theme)
        self.console.push_theme(self.theme.rich_theme)
        self.note(f"theme {self.theme.name}")
        self.on_change()
        return True

    def cmd_mode(self, arg: str) -> bool:
        if not arg:
            arg = "emacs" if self.settings.editing_mode == "vi" else "vi"
        self.settings.set("editing_mode", arg)
        self.note(f"{self.settings.editing_mode} key bindings")
        self.on_change()
        return True

    def cmd_project(self, arg: str) -> bool:
        grid = Table.grid(padding=(0, 2))
        grid.add_column(no_wrap=True)
        grid.add_column(overflow="fold")
        n = len(self.store)
        for key, value in (
            ("Project", self.project.name),
            ("Root", short_path(self.project.root)),
            ("Aliases", f"{n} · {short_path(self.project.aliases_file)}"),
        ):
            grid.add_row(Text("  " + key, style="flare.fg"), Text(value, style="flare.label"))
        self.print(grid)
        self.console.print()
        return True

    def cmd_clear(self, arg: str) -> bool:
        self.console.clear()
        return True

    def cmd_exit(self, arg: str) -> bool:
        self.exit_requested = True
        return True

    def cmd_help(self, arg: str) -> bool:
        def section(title: str) -> None:
            self.console.print(Text("  " + title, style="flare.accent.bold"))

        def rows(items: list[tuple[str, str]]) -> None:
            grid = Table.grid(padding=(0, 2))
            grid.add_column(no_wrap=True)
            grid.add_column()
            for key, desc in items:
                grid.add_row(Text("  " + key, style="flare.label"), Text(desc, style="flare.muted"))
            self.print(grid)
            self.console.print()

        section("requests")
        rows([
            ("curl -X GET https://api.dev/users", "paste any curl command"),
            ("GET api.dev/users", "or just a method and a URL (https is assumed)"),
            ("POST :8000/login username=arthur password=1234", "fields after the URL are sent as a JSON body"),
            ("age:=33  admin:=true  page==2  X-Token:abc", "raw JSON value · query parameter · header"),
            ("POST :8000/users -d '{\"name\":\"ada\"}'", ":port means localhost; -d JSON bodies are sent as JSON"),
            ("-H 'Authorization: Bearer $TOKEN'", "$VARS come from your environment when sent"),
            ("-L  -k  -v  -u user:pass  -m 5", "follow redirects · insecure · show request · auth · timeout"),
        ])
        section("aliases  ·  saved per project")
        rows([
            ("/alias get_all_users GET api.dev/users", "save a request"),
            ("/alias get_user GET api.dev/users/{id}", "{placeholders} are filled when called"),
            ("/get_user 42   ·   /get_user id=42", "call it; extra arguments are appended (fields, -v, -H …)"),
        ])
        section("commands")
        rows([(f"/{name} {args}".rstrip(), desc) for name, (args, desc) in COMMANDS.items()])
        section("keys")
        rows([
            ("Enter", "send (a trailing \\ continues on the next line)"),
            ("Alt+Enter · Ctrl+J", "new line"),
            ("Tab · →", "complete · accept the grey suggestion"),
            ("↑ ↓ · Ctrl+R", "history · search history"),
            ("Ctrl+O", "edit the input in $EDITOR"),
            ("Esc · i", "vi normal · insert mode (/mode vi)"),
            ("Ctrl+C · Ctrl+D", "clear input or cancel a request · exit"),
        ])
        return True

