"""The interactive prompt: ember's filled input bar, key bar and mode line, for HTTP."""

from __future__ import annotations

import re
import sys
import time
from typing import Iterable

from prompt_toolkit.application import Application
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.completion import CompleteEvent, Completer, Completion, ThreadedCompleter
from prompt_toolkit.cursor_shapes import ModalCursorShapeConfig
from prompt_toolkit.document import Document
from prompt_toolkit.enums import DEFAULT_BUFFER, EditingMode
from prompt_toolkit.filters import Condition, emacs_mode, has_completions, has_focus, has_selection, vi_insert_mode, vi_mode, vi_navigation_mode
from prompt_toolkit.formatted_text import StyleAndTextTuples
from prompt_toolkit.history import FileHistory, InMemoryHistory
from prompt_toolkit.input.ansi_escape_sequences import ANSI_SEQUENCES
from prompt_toolkit.key_binding import KeyBindings, KeyBindingsBase, KeyPressEvent
from prompt_toolkit.key_binding.bindings.auto_suggest import load_auto_suggest_bindings
from prompt_toolkit.key_binding.key_bindings import merge_key_bindings
from prompt_toolkit.key_binding.vi_state import InputMode
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout import ConditionalContainer, Float, FloatContainer, FormattedTextControl, HSplit, Layout, VSplit, Window
from prompt_toolkit.layout.controls import BufferControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.layout.menus import CompletionsMenu
from prompt_toolkit.layout.processors import AppendAutoSuggestion, Processor, Transformation, TransformationInput
from prompt_toolkit.lexers import Lexer
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.styles import DynamicStyle
from prompt_toolkit.utils import get_cwidth
from rich.text import Text

from flare import __version__, render
from flare.banner import wordmark
from flare.project import short_path
from flare.request import ITEM, METHODS, _FLAG_OPTS, _VALUE_OPTS, is_complete
from flare.session import COMMANDS, Session, describe
from flare.theme import PALETTES

MENU_HEIGHT = 8

# Same trick as ember: ask for xterm's modifyOtherKeys so Shift+Enter can insert a newline.
ENABLE_MODIFIED_KEYS = "\x1b[>4;1m"
DISABLE_MODIFIED_KEYS = "\x1b[>4;0m"


def _register_modified_key_sequences() -> None:
    for mod in range(2, 9):
        for seq in (f"\x1b[27;{mod};13~", f"\x1b[13;{mod}u"):
            ANSI_SEQUENCES[seq] = Keys.ControlJ
        if mod == 2:
            continue
        for code in (9, 27, 127, *range(32, 127)):
            for seq in (f"\x1b[27;{mod};{code}~", f"\x1b[{code};{mod}u"):
                ANSI_SEQUENCES.setdefault(seq, Keys.Ignore)


_register_modified_key_sequences()

_FLAG_HELP = {
    "-X": "method", "-H": "header 'Name: value'", "-d": "body", "--json": "JSON body",
    "-u": "basic auth user:pass", "-L": "follow redirects", "-k": "skip TLS verification",
    "-v": "show the request too", "-I": "HEAD request", "-G": "send -d data as query string",
    "-m": "timeout in seconds", "-A": "user agent", "-b": "cookie", "--data-urlencode": "url-encoded field",
}
# Whitespace, or a shell word: unquoted runs and quoted parts glued together (username='arthur').
_TOKEN = re.compile(r"""(\s+)|((?:[^\s'"]+|'[^']*'?|"(?:\\.|[^"\\])*"?)+)""")
_VAR = re.compile(r"\$\{\w+\}|\$\w+")


def _width(fragments: StyleAndTextTuples) -> int:
    return sum(get_cwidth(f[1]) for f in fragments)


def _truncate(fragments: StyleAndTextTuples, width: int) -> StyleAndTextTuples:
    out: StyleAndTextTuples = []
    used = 0
    for style, text, *_ in fragments:
        if used + get_cwidth(text) >= width:
            out.append((style, text[: max(0, width - used - 1)] + "…"))
            break
        out.append((style, text))
        used += get_cwidth(text)
    return out


class InputLexer(Lexer):
    """Colours the input: /commands, aliases, the method, flags, quoted strings and $VARS."""

    def __init__(self, session: Session):
        self.session = session

    def _word(self, word: str, style: str) -> StyleAndTextTuples:
        out: StyleAndTextTuples = []
        pos = 0
        for m in _VAR.finditer(word):
            out += [(style, word[pos:m.start()]), ("class:input.var", m.group())]
            pos = m.end()
        out.append((style, word[pos:]))
        return [f for f in out if f[1]]

    def lex_document(self, document: Document):
        lines = document.lines

        def get_line(n: int) -> StyleAndTextTuples:
            out: StyleAndTextTuples = []
            first = n == 0
            expect_url = False
            prev = ""
            for m in _TOKEN.finditer(lines[n]):
                space, word = m.groups()
                if space:
                    out.append(("", space))
                    continue
                if word[0] in "'\"":
                    quoted = word
                    out += self._word(quoted, "class:input.string")
                elif first and word.startswith("/"):
                    name = word[1:]
                    style = "class:input.command" if name in COMMANDS else "class:input.alias" if name in self.session.store else "class:input.unknown"
                    out.append((style, word))
                elif (first or prev in ("-X", "--request")) and word.upper() in METHODS:
                    out.append(("class:input.method", word))
                    expect_url = True
                elif word.startswith("-"):
                    out.append(("class:input.flag", word))
                elif first and word == "curl":
                    out.append(("class:input.flag", word))
                    expect_url = True
                elif "://" in word or expect_url and prev not in _VALUE_OPTS:
                    out += self._word(word, "class:input.url")
                    expect_url = False
                elif prev not in _VALUE_OPTS and (item := ITEM.fullmatch(word)):
                    key, sep, value = item.groups()
                    out += [("class:input.key", key), ("class:input.sep", sep), *self._word(value, "class:input.string")]
                else:
                    out += self._word(word, "")
                first = False
                prev = word or ""
            return out

        return get_line


class FlareCompleter(Completer):
    def __init__(self, session: Session):
        self.session = session

    def get_completions(self, document: Document, event: CompleteEvent) -> Iterable[Completion]:
        text = document.text_before_cursor
        if "\n" in text:
            return
        if re.fullmatch(r"/[\w.-]*", text):
            word = text[1:]
            for name, (args, desc) in COMMANDS.items():
                if name.startswith(word):
                    yield Completion(name, -len(word), display="/" + name, display_meta=desc)
            for name, command in sorted(self.session.store.aliases.items()):
                if name.startswith(word):
                    method, url, _ = describe(command)
                    yield Completion(name, -len(word), display="/" + name, display_meta=f"{method} {url}")
            return
        if m := re.fullmatch(r"/(\w+)\s+(\S*)", text):
            command, word = m.groups()
            choices: dict[str, str] = {}
            if command in ("unalias", "edit", "alias"):
                choices = {name: describe(cmd)[1] for name, cmd in self.session.store.aliases.items()}
            elif command == "theme":
                choices = {name: "" for name in PALETTES}
            elif command == "mode":
                choices = {"vi": "", "emacs": ""}
            elif command == "headers":
                choices = {"on": "", "off": ""}
            for name, meta in sorted(choices.items()):
                if name.startswith(word):
                    yield Completion(name, -len(word), display_meta=meta)
            return
        if re.fullmatch(r"[A-Za-z]+", text):
            for method in METHODS:
                if method.startswith(text.upper()):
                    yield Completion(method, -len(text))
            return
        word = document.get_word_before_cursor(WORD=True)
        if word.startswith("-") and not text.lstrip().startswith("/"):
            for flag in sorted({*_VALUE_OPTS, *_FLAG_OPTS}):
                if flag.startswith(word) and flag in _FLAG_HELP:
                    yield Completion(flag, -len(word), display_meta=_FLAG_HELP[flag])


class Placeholder(Processor):
    def __init__(self, text: str):
        self.text = text

    def apply_transformation(self, ti: TransformationInput) -> Transformation:
        if ti.lineno == 0 and not ti.document.text:
            return Transformation([*ti.fragments, ("class:placeholder", self.text)])
        return Transformation(ti.fragments)


class Repl:
    def __init__(self, session: Session, warnings: list[str] | None = None):
        self.session = session
        self.warnings = warnings or []
        self.flash: tuple[str, float] | None = None
        self.shift_enter_works = False
        try:
            session.project.ensure()
            history = FileHistory(str(session.project.history_file))
        except OSError:
            history = InMemoryHistory()
        self.buffer = Buffer(
            name=DEFAULT_BUFFER,
            multiline=True,
            history=history,
            completer=ThreadedCompleter(FlareCompleter(session)),
            complete_while_typing=True,
            auto_suggest=AutoSuggestFromHistory(),
            enable_history_search=Condition(lambda: "\n" not in self.buffer.text),
            on_text_changed=lambda _: setattr(self, "flash", None),
        )
        self.app = self._build_app()

    # ── layout ────────────────────────────────────────────────────────────

    def _build_app(self) -> Application:
        pad = lambda **kw: Window(style="class:bar", **kw)  # noqa: E731
        input_window = Window(
            BufferControl(
                buffer=self.buffer,
                lexer=InputLexer(self.session),
                input_processors=[AppendAutoSuggestion(), Placeholder("Paste a curl command, type GET <url>, or /help…")],
            ),
            height=Dimension(min=1, max=16),
            wrap_lines=True,
            get_line_prefix=self._bar_prefix,
            dont_extend_height=True,
            style="class:bar",
        )
        bar = HSplit([
            pad(height=1),
            VSplit([
                pad(width=2),
                input_window,
                Window(FormattedTextControl(self._bar_counter), dont_extend_width=True, style="class:bar"),
                pad(width=2),
            ]),
            pad(height=1),
        ])
        keybar = Window(FormattedTextControl(self._keybar), height=1)
        modeline = Window(FormattedTextControl(self._modeline), height=1)
        reserve = ConditionalContainer(Window(height=MENU_HEIGHT), filter=has_completions)
        body = HSplit([bar, Window(height=1), keybar, Window(height=1), modeline, reserve])
        root = FloatContainer(
            content=body,
            floats=[Float(xcursor=True, ycursor=True, content=CompletionsMenu(max_height=MENU_HEIGHT, scroll_offset=1))],
        )
        app = Application(
            layout=Layout(root),
            key_bindings=self._bindings(),
            style=DynamicStyle(lambda: self.session.theme.pt_style),
            include_default_pygments_style=False,
            erase_when_done=True,
            mouse_support=False,
            cursor=ModalCursorShapeConfig(),
        )
        app.ttimeoutlen = 0.05
        app.key_processor.after_key_press += lambda _: app.invalidate()
        return app

    def _bar_prefix(self, line_number: int, wrap_count: int) -> StyleAndTextTuples:
        if wrap_count:
            return [("class:bar.cont", "  ")]
        return [("class:bar.prompt", "> ")] if line_number == 0 else [("class:bar.cont", "· ")]

    def _bar_counter(self) -> StyleAndTextTuples:
        return [("class:bar.count", f"  [{self.session.count + 1}]")]

    def _vi_mode(self) -> str | None:
        if self.app.editing_mode != EditingMode.VI:
            return None
        mode = self.app.vi_state.input_mode
        return "NORMAL" if mode == InputMode.NAVIGATION else "REPLACE" if mode == InputMode.REPLACE else "INSERT"

    def keybar_items(self) -> list[tuple[str, str]]:
        if self.buffer.complete_state:
            return [("NEXT", "Tab"), ("ACCEPT", "Enter"), ("CLOSE", "Esc")]
        items: list[tuple[str, str]] = []
        mode = self._vi_mode()
        if mode == "INSERT":
            items.append(("NORMAL MODE", "Esc"))
        elif mode:
            items.append(("INSERT MODE", "i"))
        if not is_complete(self.buffer.text):
            items.append(("NEWLINE", "Enter"))
        else:
            items.append(("SEND", "Enter"))
        if self.session.last_command is not None:
            items.append(("SAVE AS ALIAS", "/save name"))
        items += [("ALIASES", "/aliases"), ("HELP", "/help"), ("EXIT", "Ctrl+D")]
        if is_complete(self.buffer.text):
            items.append(("NEWLINE", "Shift+Enter" if self.shift_enter_works else "Alt+Enter"))
        return items  # least important last: they're dropped first on narrow terminals

    def _keybar(self) -> StyleAndTextTuples:
        width = self.app.output.get_size().columns - 4
        items = self.keybar_items()

        def draw(entries: list[tuple[str, str]]) -> StyleAndTextTuples:
            out: StyleAndTextTuples = [("", "  ")]
            for i, (label, key) in enumerate(entries):
                if i:
                    out.append(("class:keybar.sep", "  |  "))
                out += [("class:keybar.label", label), ("class:keybar.key", f": {key}")]
            return out

        while len(items) > 1 and _width(draw(items)) > width + 2:
            items.pop()
        return draw(items)

    def _modeline(self) -> StyleAndTextTuples:
        out: StyleAndTextTuples = []
        if mode := self._vi_mode():
            out += [("class:modeline.mode", f"[{mode}]"), ("", "  ")]
        else:
            out.append(("", "  "))
        if self.flash and time.monotonic() < self.flash[1]:
            return out + [("class:status.warn", self.flash[0])]
        s = self.session
        sep = ("class:status.sep", "  ·  ")
        n = len(s.store)
        out += [("class:status", s.project.name), sep, ("class:status", f"{n} alias{'es' if n != 1 else ''}")]
        if s.last is not None and s.last_ok is not None:
            resp = s.last.response
            mark = ("class:status.ok", "✓ ") if s.last_ok else ("class:status.err", "✗ ")
            out += [sep, mark, ("class:status", f"{resp.status_code} · {render.format_duration(s.last.elapsed)}")]
        elif s.last_ok is False:
            out += [sep, ("class:status.err", "✗ "), ("class:status", "failed")]
        if not s.settings.headers:
            out += [sep, ("class:status.dim", "headers hidden")]
        width = self.app.output.get_size().columns - 1
        return out if _width(out) <= width else _truncate(out, width)

    # ── keys ──────────────────────────────────────────────────────────────

    def _bindings(self) -> KeyBindingsBase:
        kb = KeyBindings()
        focused = has_focus(DEFAULT_BUFFER)
        insert_mode = emacs_mode | vi_insert_mode

        @kb.add(Keys.BracketedPaste, filter=focused)
        def _paste(event: KeyPressEvent) -> None:
            event.current_buffer.insert_text(event.data.replace("\r\n", "\n").replace("\r", "\n"))

        @kb.add("enter", filter=focused & vi_mode & vi_navigation_mode & ~has_selection)
        def _vi_enter(event: KeyPressEvent) -> None:
            if is_complete(event.current_buffer.text):
                self._submit(event)

        @kb.add("enter", filter=focused & ~has_selection & insert_mode)
        def _enter(event: KeyPressEvent) -> None:
            b = event.current_buffer
            state = b.complete_state
            if state and state.current_completion:
                b.apply_completion(state.current_completion)
                return
            if state:
                b.cancel_completion()
            if is_complete(b.text):
                self._submit(event)
            else:
                b.insert_text("\n")

        @kb.add("escape", "enter", filter=focused & insert_mode)
        @kb.add("c-j", filter=focused & insert_mode)  # also Shift+Enter, via the sequences registered above
        def _newline(event: KeyPressEvent) -> None:
            if event.key_sequence[-1].data.startswith("\x1b["):
                self.shift_enter_works = True
            event.current_buffer.insert_text("\n")

        @kb.add("tab", filter=focused & ~has_selection & insert_mode)
        def _tab(event: KeyPressEvent) -> None:
            b = event.current_buffer
            if b.complete_state:
                b.complete_next()
            else:
                b.start_completion(insert_common_part=True)

        @kb.add("s-tab", filter=focused & insert_mode & has_completions)
        def _stab(event: KeyPressEvent) -> None:
            event.current_buffer.complete_previous()

        @kb.add("escape", filter=focused & has_completions, eager=True)
        def _escape(event: KeyPressEvent) -> None:
            b = event.current_buffer
            b.cancel_completion()
            if event.app.editing_mode == EditingMode.VI and event.app.vi_state.input_mode != InputMode.NAVIGATION:
                event.app.vi_state.input_mode = InputMode.NAVIGATION
                b.cursor_position += b.document.get_cursor_left_position()

        @kb.add("c-c", filter=focused)
        def _ctrl_c(event: KeyPressEvent) -> None:
            b = event.current_buffer
            if b.text:
                b.reset()
            else:
                self.flash = ("press ctrl+d to exit", time.monotonic() + 2.5)

        @kb.add("c-d", filter=focused & Condition(lambda: not self.buffer.text))
        def _ctrl_d(event: KeyPressEvent) -> None:
            event.app.exit(result=None)

        @kb.add("c-l")
        def _clear(event: KeyPressEvent) -> None:
            event.app.renderer.clear()

        @kb.add("c-o", filter=focused)
        def _editor(event: KeyPressEvent) -> None:
            event.current_buffer.open_in_editor(validate_and_handle=False)

        return merge_key_bindings([load_auto_suggest_bindings(), kb])

    def _submit(self, event: KeyPressEvent) -> None:
        b = event.current_buffer
        text = b.text
        if text.strip():
            b.document = Document(text.strip())
            b.append_to_history()
        event.app.exit(result=text)

    # ── main loop ─────────────────────────────────────────────────────────

    def banner(self) -> None:
        c, s = self.session.console, self.session
        c.print()
        if c.width >= 48:
            for line in wordmark():
                c.print(line, overflow="crop", no_wrap=True)
        else:
            c.print(Text("  ://flare", style="flare.logo"))
        c.print()
        c.print(Text(f"  v{__version__}", style="flare.faint"))
        c.print()
        n = len(s.store)
        rows = [
            ("Project", s.project.name),
            ("Directory", short_path(s.project.root)),
            ("Aliases", f"{n}" + ("  ·  /aliases to list them" if n else "  ·  /alias <name> <request> to add one")),
            ("Theme", s.theme.name),
        ]
        width = max(len(k) for k, _ in rows) + 2
        for key, value in rows:
            c.print(Text.assemble(("  " + key.ljust(width), "flare.fg"), (value, "flare.label")))
        for warning in self.warnings:
            c.print(Text.assemble(("  ! ", "flare.warn"), (warning, "flare.muted")))
        c.print()

    def read(self) -> str | None:
        initial, self.session.next_input = self.session.next_input, ""
        vi = self.session.settings.editing_mode == "vi"
        self.app.editing_mode = EditingMode.VI if vi else EditingMode.EMACS
        self.app.timeoutlen = 0.15 if vi else 1.0

        def pre_run() -> None:
            self.buffer.reset(Document(initial, len(initial)))
            if vi:
                self.app.vi_state.input_mode = InputMode.INSERT

        interactive = sys.__stdout__.isatty()
        if interactive:
            sys.__stdout__.write(ENABLE_MODIFIED_KEYS)
            sys.__stdout__.flush()
        try:
            with patch_stdout(raw=True):
                return self.app.run(pre_run=pre_run)
        finally:
            if interactive:
                sys.__stdout__.write(DISABLE_MODIFIED_KEYS)
                sys.__stdout__.flush()

    def run(self) -> int:
        self.banner()
        while not self.session.exit_requested:
            try:
                text = self.read()
            except (EOFError, KeyboardInterrupt):
                break
            if text is None:
                break
            try:
                self.session.run(text)
            except KeyboardInterrupt:
                self.session.note("cancelled", ok=False)
        self.session.console.print(Text("  goodbye ✦", style="flare.faint"))
        return 0
