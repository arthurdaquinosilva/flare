"""Color palettes shared by the prompt (prompt_toolkit), output (rich) and syntax (pygments).

The palettes are ember's, so the two tools look like siblings.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property

from prompt_toolkit.styles import Style as PTStyle
from prompt_toolkit.styles import merge_styles, style_from_pygments_cls
from pygments.style import Style as PygmentsStyle
from pygments.token import (
    Comment,
    Error,
    Generic,
    Keyword,
    Name,
    Number,
    Operator,
    Punctuation,
    String,
    Text,
    Token,
)
from rich.syntax import PygmentsSyntaxTheme
from rich.theme import Theme as RichTheme


@dataclass(frozen=True)
class Palette:
    name: str
    fg: str
    muted: str
    faint: str
    border: str
    surface: str
    selection: str
    bar: str  # filled input bar
    label: str  # key-bar labels and banner values
    accent: str
    accent2: str
    logo: str  # the banner wordmark
    ok: str
    err: str
    warn: str
    info: str
    # syntax
    keyword: str
    builtin: str
    function: str
    klass: str
    string: str
    number: str
    comment: str
    operator: str
    decorator: str


PALETTES: dict[str, Palette] = {
    # Near-black monochrome with a single warm accent.
    "void": Palette(
        name="void",
        fg="#e7e7e7",
        muted="#8b8b8b",
        faint="#555555",
        border="#3b3b3b",
        surface="#161616",
        selection="#2b2b2b",
        bar="#24262b",
        label="#86c7c0",
        accent="#ff8a4c",
        accent2="#ffc46b",
        logo="#e879f9",
        ok="#7ee2a8",
        err="#ff6b6b",
        warn="#f2c14e",
        info="#7cc4ff",
        keyword="#ff9e6b",
        builtin="#7cc4ff",
        function="#e7e7e7",
        klass="#ffd08a",
        string="#a8d8a0",
        number="#f5a97f",
        comment="#5f5f5f",
        operator="#9a9a9a",
        decorator="#c9a0ff",
    ),
    "nebula": Palette(
        name="nebula",
        fg="#e4e1f5",
        muted="#8c87a8",
        faint="#56516e",
        border="#3a3552",
        surface="#15131f",
        selection="#2a2640",
        bar="#262238",
        label="#6ee7f9",
        accent="#b18cff",
        accent2="#6ee7f9",
        logo="#e879f9",
        ok="#6ee7b7",
        err="#fb7185",
        warn="#fcd34d",
        info="#6ee7f9",
        keyword="#c4a5ff",
        builtin="#6ee7f9",
        function="#f0ecff",
        klass="#f9a8d4",
        string="#86efac",
        number="#fda4af",
        comment="#5c5776",
        operator="#a39fc0",
        decorator="#f9a8d4",
    ),
    "matrix": Palette(
        name="matrix",
        fg="#d7f5dd",
        muted="#7a9a80",
        faint="#46604b",
        border="#2e4533",
        surface="#0f1a12",
        selection="#1f3324",
        bar="#18261c",
        label="#5eead4",
        accent="#4ade80",
        accent2="#a3e635",
        logo="#e879f9",
        ok="#4ade80",
        err="#f87171",
        warn="#facc15",
        info="#5eead4",
        keyword="#4ade80",
        builtin="#5eead4",
        function="#ecfdf0",
        klass="#a3e635",
        string="#bef264",
        number="#fde68a",
        comment="#4b6b52",
        operator="#8fb396",
        decorator="#5eead4",
    ),
}

DEFAULT_THEME = "void"


class Theme:
    def __init__(self, palette: Palette):
        self.p = palette

    @property
    def name(self) -> str:
        return self.p.name

    def method_style(self, method: str) -> str:
        """Each HTTP verb gets its own colour, so a scrollback of requests is easy to scan."""
        p = self.p
        return {
            "GET": p.info,
            "POST": p.ok,
            "PUT": p.warn,
            "PATCH": p.accent2,
            "DELETE": p.err,
        }.get(method.upper(), p.decorator)

    def status_style(self, code: int) -> str:
        p = self.p
        if code >= 500:
            return p.err
        if code >= 400:
            return p.warn
        if code >= 300:
            return p.info
        return p.ok

    @cached_property
    def pygments_style(self) -> type[PygmentsStyle]:
        p = self.p
        return type(
            f"Flare{p.name.title()}Style",
            (PygmentsStyle,),
            {
                "background_color": None,
                "highlight_color": p.selection,
                "styles": {
                    Token: p.fg,
                    Text: p.fg,
                    Comment: f"italic {p.comment}",
                    Keyword: p.keyword,
                    Keyword.Constant: f"italic {p.decorator}",  # true / false / null
                    Operator: p.operator,
                    Punctuation: p.faint,
                    Name: p.fg,
                    Name.Tag: p.klass,  # JSON keys, XML/HTML tags
                    Name.Attribute: p.builtin,
                    Name.Builtin: p.builtin,
                    Name.Function: p.function,
                    Name.Class: f"bold {p.klass}",
                    Name.Variable: p.accent2,  # $VARS in the input
                    String: p.string,
                    String.Escape: p.number,
                    Number: p.number,
                    Generic.Deleted: p.err,
                    Generic.Inserted: p.ok,
                    Generic.Heading: f"bold {p.fg}",
                    Generic.Error: p.err,
                    Error: p.err,
                },
            },
        )

    @cached_property
    def syntax_theme(self) -> PygmentsSyntaxTheme:
        return PygmentsSyntaxTheme(self.pygments_style)

    @cached_property
    def pt_style(self) -> PTStyle:
        p = self.p
        ui = PTStyle.from_dict(
            {
                "": p.fg,
                "bar": f"bg:{p.bar}",
                "bar.prompt": f"bg:{p.bar} bold {p.accent}",
                "bar.cont": f"bg:{p.bar} {p.faint}",
                "bar.count": f"bg:{p.bar} {p.faint}",
                "placeholder": p.faint,
                "keybar.label": f"bold {p.label}",
                "keybar.key": p.fg,
                "keybar.sep": p.faint,
                "modeline.mode": f"bold {p.label}",
                "status": p.muted,
                "status.dim": p.faint,
                "status.accent": p.accent,
                "status.ok": p.ok,
                "status.err": p.err,
                "status.warn": p.warn,
                "status.sep": p.faint,
                "input.command": f"bold {p.accent}",
                "input.alias": f"bold {p.label}",
                "input.unknown": p.err,
                "input.method": f"bold {p.info}",
                "input.url": f"underline {p.fg}",
                "input.flag": p.muted,
                "input.var": p.accent2,
                "input.string": p.string,
                "input.key": p.klass,
                "input.sep": p.faint,
                "auto-suggestion": p.faint,
                "selected": f"bg:{p.selection}",
                "completion-menu": f"bg:{p.surface} {p.fg}",
                "completion-menu.completion": f"bg:{p.surface} {p.fg}",
                "completion-menu.completion.current": f"bg:{p.selection} bold {p.accent}",
                "completion-menu.meta.completion": f"bg:{p.surface} {p.faint}",
                "completion-menu.meta.completion.current": f"bg:{p.selection} {p.muted}",
                "completion-menu.multi-column-meta": f"bg:{p.surface} {p.muted}",
                "scrollbar.background": f"bg:{p.surface}",
                "scrollbar.button": f"bg:{p.border}",
                "search": f"bg:{p.selection}",
                "search.current": f"bg:{p.accent} #000000",
                "search-toolbar": p.muted,
                "search-toolbar.prompt": f"bold {p.accent}",
                "search-toolbar.text": p.fg,
            }
        )
        return merge_styles([style_from_pygments_cls(self.pygments_style), ui])

    @cached_property
    def rich_theme(self) -> RichTheme:
        p = self.p
        return RichTheme(
            {
                "flare.fg": p.fg,
                "flare.muted": p.muted,
                "flare.faint": p.faint,
                "flare.border": p.border,
                "flare.accent": p.accent,
                "flare.accent2": p.accent2,
                "flare.ok": p.ok,
                "flare.err": p.err,
                "flare.warn": p.warn,
                "flare.info": p.info,
                "flare.label": f"bold {p.label}",
                "flare.key": p.klass,
                "flare.var": p.accent2,
                "flare.accent.bold": f"bold {p.accent}",
                "flare.logo": f"bold {p.logo}",
                "flare.err.bold": f"bold {p.err}",
                "flare.fg.bold": f"bold {p.fg}",
                "flare.url": p.fg,
                "repr.number": p.number,
                "repr.str": p.string,
                "repr.url": f"underline {p.info}",
                "table.header": f"bold {p.accent}",
                "rule.line": p.border,
            }
        )


def get_theme(name: str | None) -> Theme:
    return Theme(PALETTES.get(name or DEFAULT_THEME, PALETTES[DEFAULT_THEME]))
