import io
import json

import httpx
import pytest
from rich.console import Console

from flare.config import Settings
from flare.project import Project
from flare.session import Session


def echo_handler(request: httpx.Request) -> httpx.Response:
    """Echoes what it received, so tests can check what was sent."""
    if request.url.path == "/missing":
        return httpx.Response(404, json={"error": "not found"})
    if request.url.path == "/png":
        return httpx.Response(200, content=b"\x89PNG\r\n\x1a\n\x00\x00", headers={"Content-Type": "image/png"})
    body = request.content.decode() if request.content else None
    return httpx.Response(200, json={
        "method": request.method,
        "url": str(request.url),
        "headers": dict(request.headers),
        "body": json.loads(body) if body and body.startswith("{") else body,
    })


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    return Project.locate(root, base=tmp_path / "data")


@pytest.fixture
def session(project):
    console = Console(file=io.StringIO(), width=100, force_terminal=False)
    return Session(Settings(), project, console=console, transport=httpx.MockTransport(echo_handler), env={"TOKEN": "s3cret"})


def output(session) -> str:
    return session.console.file.getvalue()
