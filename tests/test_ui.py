from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document

from flare.banner import pixel_rows
from flare.ui import FlareCompleter


def complete(session, text):
    return [c.text for c in FlareCompleter(session).get_completions(Document(text), CompleteEvent())]


def test_completes_commands_aliases_and_methods(session):
    session.run("/alias get_all_users GET api.dev/users")
    assert complete(session, "/get") == ["get_all_users"]
    assert "aliases" in complete(session, "/al")
    assert complete(session, "/unalias g") == ["get_all_users"]
    assert complete(session, "po") == ["POST"]
    assert "-H" in complete(session, "GET api.dev -")


def test_wordmark():
    rows = pixel_rows("://flare")
    assert len(rows) == 4
    assert set("".join(rows)) <= set("█▀▄ ")
