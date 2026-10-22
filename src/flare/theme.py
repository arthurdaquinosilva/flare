"""The color palette shared by the prompt (prompt_toolkit), output (rich) and syntax (pygments).

It is pitch, the palette every one of these tools shares; only the accent differs.
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
    # pitch: cool blue/violet hues on a pitch-black terminal, shared by all the tools;
    # each one gets its own accent (flare's is yellow).
    "pitch": Palette(
        name="pitch",
        fg="#c0caf5",
        muted="#737aa2",
        faint="#565f89",
        border="#2a2e42",
        surface="#0b0d14",
        selection="#161925",
        bar="#161925",
        label="#bb9af7",
        accent="#e0af68",
        accent2="#ff9e64",
        logo="#e0af68",
        ok="#9ece6a",
        err="#f7768e",
        warn="#e0af68",
        info="#7aa2f7",
        keyword="#bb9af7",
        builtin="#7dcfff",
        function="#7aa2f7",
        klass="#73daca",
        string="#9ece6a",
        number="#ff9e64",
        comment="#565f89",
        operator="#a9b1d6",
        decorator="#e0af68",
    ),
}

DEFAULT_THEME = "pitch"


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
                "rule": p.border,
                "prompt": p.muted,
                "prompt.cont": p.faint,
                "footer.mode": p.muted,
                "footer.hint": p.faint,
                "shortcut.key": f"bold {p.muted}",
                "shortcut.desc": p.faint,
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
                # Completions are a plain list under the prompt, like querky's: no box, accent on the current one.
                "completion-menu": p.fg,
                "completion-menu.completion": p.fg,
                "completion-menu.completion.current": f"bold {p.accent}",
                "completion-menu.meta.completion": p.faint,
                "completion-menu.meta.completion.current": p.accent,
                "completion-menu.multi-column-meta": p.muted,
                "scrollbar.background": "",
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
