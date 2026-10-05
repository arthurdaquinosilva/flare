"""Projects and their aliases.

A project is the git repository you're in (or the current directory outside one). Each project
keeps its own aliases and history under the data directory, so `/get_all_users` in one repo never
collides with a same-named alias in another, and nothing is written into the repo itself.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
from dataclasses import dataclass
from pathlib import Path

NAME = re.compile(r"[A-Za-z_][\w.-]*")
PLACEHOLDER = re.compile(r"\{(\w+)\}")


class AliasError(ValueError):
    pass


def data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")) / "flare"


def short_path(path: str | os.PathLike) -> str:
    path = str(path)
    home = os.path.expanduser("~")
    if path == home or path.startswith(home + os.sep):
        path = "~" + path[len(home):]
    return path


def find_root(start: Path) -> Path:
    start = start.resolve()
    for d in (start, *start.parents):
        if (d / ".git").exists():
            return d
    return start


@dataclass
class Project:
    root: Path
    data_dir: Path

    @classmethod
    def locate(cls, start: Path | None = None, base: Path | None = None) -> "Project":
        root = find_root(start or Path.cwd())
        slug = re.sub(r"[^\w.-]", "_", root.name) or "root"
        digest = hashlib.sha1(str(root).encode()).hexdigest()[:8]
        return cls(root, (base or data_home()) / "projects" / f"{slug}-{digest}")

    @property
    def name(self) -> str:
        return self.root.name or str(self.root)

    @property
    def aliases_file(self) -> Path:
        return self.data_dir / "aliases.json"

    @property
    def history_file(self) -> Path:
        return self.data_dir / "history"

    def ensure(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)


class AliasStore:
    """Alias name → the command exactly as typed (environment variables left unexpanded)."""

    def __init__(self, project: Project):
        self.project = project
        self.aliases: dict[str, str] = {}
        self.load()

    def load(self) -> None:
        path = self.project.aliases_file
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError) as e:
            raise AliasError(f"could not read {path}: {e}") from None
        self.aliases = {k: v["command"] for k, v in data.get("aliases", {}).items()}

    def save(self) -> None:
        self.project.ensure()
        data = {
            "project": str(self.project.root),
            "aliases": {name: {"command": cmd} for name, cmd in sorted(self.aliases.items())},
        }
        tmp = self.project.aliases_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2) + "\n")
        tmp.replace(self.project.aliases_file)

    def set(self, name: str, command: str, reserved: tuple[str, ...] = ()) -> None:
        name = name.lstrip("/")
        if not NAME.fullmatch(name):
            raise AliasError(f"bad alias name {name!r}: use letters, digits, _ . or -")
        if name in reserved:
            raise AliasError(f"/{name} is a built-in command")
        if not command.strip():
            raise AliasError("an alias needs a request to save")
        self.aliases[name] = command.strip()
        self.save()

    def remove(self, name: str) -> None:
        name = name.lstrip("/")
        if name not in self.aliases:
            raise AliasError(f"no alias /{name} in this project")
        del self.aliases[name]
        self.save()

    def get(self, name: str) -> str | None:
        return self.aliases.get(name.lstrip("/"))

    def __contains__(self, name: str) -> bool:
        return name.lstrip("/") in self.aliases

    def __len__(self) -> int:
        return len(self.aliases)


def placeholders(command: str) -> list[str]:
    seen: list[str] = []
    for name in PLACEHOLDER.findall(command):
        if name not in seen:
            seen.append(name)
    return seen


def expand(command: str, args: list[str]) -> str:
    """Fill an alias's {placeholders}: `id=42` by name, bare values in order; leftovers are appended."""
    names = placeholders(command)
    values: dict[str, str] = {}
    extra: list[str] = []
    positional: list[str] = []
    for arg in args:
        key, sep, value = arg.partition("=")
        if sep and key in names and key not in values:
            values[key] = value
        else:
            positional.append(arg)
    for name in names:
        if name not in values and positional:
            values[name] = positional.pop(0)
    extra = positional
    missing = [n for n in names if n not in values]
    if missing:
        raise AliasError("missing " + ", ".join(f"{{{n}}}" for n in missing))
    out = PLACEHOLDER.sub(lambda m: values[m.group(1)], command)
    if extra:
        out += " " + shlex.join(extra)
    return out
