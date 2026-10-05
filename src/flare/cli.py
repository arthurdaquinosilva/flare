"""Command-line entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from flare import __version__
from flare.theme import PALETTES

USAGE = """flare [--project DIR] [--theme NAME] [--vi] [request …]

  flare                                   interactive
  flare GET api.dev/users                 send one request and exit
  flare curl -X POST api.dev/users -d …   curl syntax works too
  flare /get_all_users                    run a saved alias of this project
  flare /get_all_users | jq .             piped output is the bare body"""


def _split_argv(argv: list[str]) -> tuple[list[str], list[str]]:
    """flare's own options come first; everything from the first other token on is the request."""
    own: list[str] = []
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok in ("--project", "--theme"):
            own += argv[i:i + 2]
            i += 2
        elif tok.startswith(("--project=", "--theme=")) or tok in ("--vi", "--version", "-h", "--help"):
            own.append(tok)
            i += 1
        else:
            break
    return own, argv[i:]


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    own, request = _split_argv(argv)
    parser = argparse.ArgumentParser(prog="flare", usage=USAGE, description="A calm, beautiful terminal HTTP client.")
    parser.add_argument("--project", type=Path, help="use this directory's project (default: the git repo you're in)")
    parser.add_argument("--theme", choices=list(PALETTES), help="color theme")
    parser.add_argument("--vi", action="store_true", help="vi key bindings")
    parser.add_argument("--version", action="version", version=f"flare {__version__}")
    opts = parser.parse_args(own)

    import shlex

    from flare.config import load_settings
    from flare.project import AliasError, Project
    from flare.session import Session

    settings, warnings = load_settings()
    if opts.theme:
        settings.theme = opts.theme
    if opts.vi:
        settings.editing_mode = "vi"
    project = Project.locate(opts.project)
    try:
        session = Session(settings, project)
    except AliasError as e:
        print(f"flare: {e}", file=sys.stderr)
        return 1

    if request:
        for w in warnings:
            print(f"flare: {w}", file=sys.stderr)
        session.raw = not sys.stdout.isatty()
        return 0 if session.run(shlex.join(request)) else 1

    if not sys.stdin.isatty():
        ok = True
        session.raw = not sys.stdout.isatty()
        for line in sys.stdin.read().splitlines():
            ok &= session.run(line)
        return 0 if ok else 1

    from flare.ui import Repl

    return Repl(session, warnings).run()
