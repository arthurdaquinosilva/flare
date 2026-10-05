"""Turning what was typed — a curl command or the short `METHOD url` form — into a request spec."""

from __future__ import annotations

import json
import os
import re
import shlex
from dataclasses import dataclass, field
from typing import Mapping
from urllib.parse import urlencode

METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")

# Options that take a value, by every spelling curl accepts.
_VALUE_OPTS = {
    "-X": "method", "--request": "method",
    "-H": "header", "--header": "header",
    "-d": "data", "--data": "data", "--data-raw": "data", "--data-binary": "data", "--data-ascii": "data",
    "--data-urlencode": "data_urlencode",
    "--json": "json",
    "-u": "user", "--user": "user",
    "-A": "agent", "--user-agent": "agent",
    "-e": "referer", "--referer": "referer",
    "-b": "cookie", "--cookie": "cookie",
    "-m": "timeout", "--max-time": "timeout",
    "--connect-timeout": "timeout",
    "--url": "url",
}
# Flags without a value. The ones mapped to None only change how curl prints, so they're accepted and ignored.
_FLAG_OPTS = {
    "-L": "follow", "--location": "follow",
    "-k": "insecure", "--insecure": "insecure",
    "-I": "head", "--head": "head",
    "-G": "get", "--get": "get",
    "-v": "verbose", "--verbose": "verbose",
    "-i": None, "--include": None,
    "-s": None, "--silent": None,
    "-S": None, "--show-error": None,
    "-f": None, "--fail": None,
    "-N": None, "--no-buffer": None,
    "-#": None, "--progress-bar": None,
    "--compressed": None, "--http1.1": None, "--http2": None,
}
_UNSUPPORTED = {"-F": "multipart forms (-F)", "--form": "multipart forms (--form)", "-o": "-o (use /write <file>)",
                "--output": "--output (use /write <file>)", "-T": "uploads (-T)", "--upload-file": "uploads (--upload-file)"}
_VAR = re.compile(r"\$\{(\w+)\}|\$(\w+)")
# Request items after the URL, as in httpie: the earliest separator wins (`a=b:c` is a field, `X-A:b=c` a header).
ITEM = re.compile(r"([^=:\s]+)(:=|==|=|:)(.*)", re.S)


class ParseError(ValueError):
    pass


@dataclass
class RequestSpec:
    method: str = "GET"
    url: str = ""
    headers: list[tuple[str, str]] = field(default_factory=list)
    data: str | None = None
    auth: tuple[str, str] | None = None
    follow_redirects: bool = False
    verify: bool = True
    timeout: float | None = None
    verbose: bool = False

    def header(self, name: str) -> str | None:
        for key, value in self.headers:
            if key.lower() == name.lower():
                return value
        return None

    def set_default_header(self, name: str, value: str) -> None:
        if self.header(name) is None:
            self.headers.append((name, value))


def split_command(text: str) -> list[str]:
    """Shell-style split; a backslash at the end of a line continues it, as in a pasted curl command."""
    text = re.sub(r"\\\r?\n", " ", text)
    try:
        return shlex.split(text)
    except ValueError:
        raise ParseError("unbalanced quotes") from None


def is_complete(text: str) -> bool:
    """False while the input clearly continues on the next line (trailing backslash or an open quote)."""
    if text.rstrip(" ").endswith("\\"):
        return False
    try:
        split_command(text)
    except ParseError:
        return False
    return True


def expand_vars(token: str, env: Mapping[str, str]) -> str:
    """Expand $NAME and ${NAME} from the environment, so secrets stay out of saved aliases."""

    def sub(m: re.Match) -> str:
        name = m.group(1) or m.group(2)
        if name not in env:
            raise ParseError(f"${name} is not set")
        return env[name]

    return _VAR.sub(sub, token)


def normalize_url(url: str) -> str:
    """`:8000/x` → http://localhost:8000/x; no scheme → https (http for local hosts)."""
    if url.startswith(":"):
        return "http://localhost" + url
    if "://" in url:
        return url
    host = url.split("/", 1)[0].split(":", 1)[0]
    local = host in ("localhost", "0.0.0.0") or host.startswith("127.") or host.endswith(".local")
    return ("http://" if local else "https://") + url


def _looks_like_json(body: str) -> bool:
    if not body.lstrip().startswith(("{", "[")):
        return False
    try:
        json.loads(body)
    except ValueError:
        return False
    return True


def _explode(tokens: list[str]) -> list[str]:
    """Split bundled short flags (-sSL) and attached values (-XPOST, --data=x) into separate tokens."""
    out: list[str] = []
    for tok in tokens:
        if tok.startswith("--") and "=" in tok and tok.split("=", 1)[0] in _VALUE_OPTS:
            out += tok.split("=", 1)
        elif re.fullmatch(r"-[A-Za-z#]{2,}", tok) and all(f"-{c}" in _FLAG_OPTS for c in tok[1:]):
            out += [f"-{c}" for c in tok[1:]]
        elif len(tok) > 2 and tok[0] == "-" and tok[1] != "-" and tok[:2] in _VALUE_OPTS:
            out += [tok[:2], tok[2:]]
        else:
            out.append(tok)
    return out


def parse(text: str, env: Mapping[str, str] | None = None) -> RequestSpec:
    env = os.environ if env is None else env
    tokens = split_command(text)
    if tokens and tokens[0] == "curl":
        tokens = tokens[1:]
    if not tokens:
        raise ParseError("nothing to send")

    spec = RequestSpec()
    method: str | None = None
    if tokens[0].upper() in METHODS:
        method = tokens.pop(0).upper()

    data: list[str] = []
    fields: dict[str, object] = {}
    query: list[tuple[str, str]] = []
    get = head = False
    tokens = _explode(tokens)
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        i += 1
        if tok in _UNSUPPORTED:
            raise ParseError(f"{_UNSUPPORTED[tok]} not supported yet")
        if tok in _FLAG_OPTS:
            kind = _FLAG_OPTS[tok]
            spec.follow_redirects |= kind == "follow"
            spec.verify &= kind != "insecure"
            spec.verbose |= kind == "verbose"
            head |= kind == "head"
            get |= kind == "get"
            continue
        if tok in _VALUE_OPTS:
            if i >= len(tokens):
                raise ParseError(f"{tok} needs a value")
            kind, value = _VALUE_OPTS[tok], expand_vars(tokens[i], env)
            i += 1
            if kind == "method":
                method = value.upper()
            elif kind == "header":
                name, sep, val = value.partition(":")
                if not sep or not name.strip():
                    raise ParseError(f"bad header {value!r} (expected 'Name: value')")
                spec.headers.append((name.strip(), val.strip()))
            elif kind == "data":
                data.append(value)
            elif kind == "data_urlencode":
                name, sep, val = value.partition("=")
                data.append(urlencode({name: val}) if sep else urlencode({"": value})[1:])
            elif kind == "json":
                data.append(value)
                spec.set_default_header("Content-Type", "application/json")
                spec.set_default_header("Accept", "application/json")
            elif kind == "user":
                user, _, password = value.partition(":")
                spec.auth = (user, password)
            elif kind == "agent":
                spec.headers.append(("User-Agent", value))
            elif kind == "referer":
                spec.headers.append(("Referer", value))
            elif kind == "cookie":
                spec.headers.append(("Cookie", value))
            elif kind == "timeout":
                try:
                    spec.timeout = float(value)
                except ValueError:
                    raise ParseError(f"{tok} expects seconds, got {value!r}") from None
            elif kind == "url":
                spec.url = value
            continue
        if tok.startswith("-") and len(tok) > 1:
            raise ParseError(f"unknown option {tok}")
        if not spec.url:
            spec.url = expand_vars(tok, env)
            continue
        item = ITEM.fullmatch(tok)
        if not item:
            raise ParseError(f"unexpected argument {tok!r} (fields look like key=value)")
        key, sep, value = item.group(1), item.group(2), expand_vars(item.group(3), env)
        if sep == "=":
            fields[key] = value
        elif sep == ":=":
            try:
                fields[key] = json.loads(value)
            except ValueError:
                raise ParseError(f"{key}:= expects JSON, got {value!r}") from None
        elif sep == "==":
            query.append((key, value))
        else:
            spec.headers.append((key, value.strip()))

    if not spec.url:
        raise ParseError("missing URL")
    spec.url = normalize_url(spec.url)
    if query:
        spec.url += ("&" if "?" in spec.url else "?") + urlencode(query)
    if fields:
        if data:
            raise ParseError("send either key=value fields or -d data, not both")
        data.append(json.dumps(fields, ensure_ascii=False))
        spec.set_default_header("Content-Type", "application/json")
        spec.set_default_header("Accept", "application/json")

    if data and get:
        spec.url += ("&" if "?" in spec.url else "?") + "&".join(data)
    elif data:
        spec.data = "&".join(data)
        # curl would label a JSON body as a form; nobody means that.
        spec.set_default_header("Content-Type", "application/json" if _looks_like_json(spec.data) else "application/x-www-form-urlencoded")
    spec.method = method or ("HEAD" if head else "POST" if spec.data is not None else "GET")
    return spec
