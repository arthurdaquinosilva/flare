import json

from conftest import output

from flare.session import Session


def test_request_is_sent_and_shown(session):
    assert session.run("""curl -X POST api.dev/users -H 'Authorization: Bearer $TOKEN' -d '{"name": "ada"}'""")
    sent = json.loads(session.last.response.text)
    assert sent["method"] == "POST"
    assert sent["headers"]["authorization"] == "Bearer s3cret"
    assert sent["body"] == {"name": "ada"}
    out = output(session)
    assert '"name": "ada"' in out
    assert "╰─ ✓ 200 OK" in out


def test_alias_lifecycle(session, project):
    assert session.run("/alias get_user GET api.dev/users/{id}")
    assert session.run("/get_user 42")
    assert json.loads(session.last.response.text)["url"] == "https://api.dev/users/42"

    session.run("GET api.dev/health")
    assert session.run("/save health")
    assert Session(session.settings, project).store.get("health") == "GET api.dev/health"  # saved to disk

    assert session.run("/edit get_user")
    assert session.next_input == "/alias get_user GET api.dev/users/{id}"
    assert session.run("/unalias get_user")
    assert not session.run("/get_user 42")
    assert "unknown command /get_user" in output(session)


def test_secrets_stay_unexpanded_in_aliases(session):
    session.run("/alias me GET api.dev/me -H 'Authorization: Bearer $TOKEN'")
    assert "$TOKEN" in session.store.get("me")


def test_failures_are_reported(session):
    assert not session.run("GET api.dev/missing")
    assert "✗ 404 Not Found" in output(session)
    assert not session.run("/alias help GET api.dev")
    assert not session.run("/alias broken curl -H 'X: 1'")
    assert "not saved: missing URL" in output(session)


def test_binary_body_and_write(session, tmp_path):
    session.run("GET api.dev/png")
    assert "binary body" in output(session)
    target = tmp_path / "img.png"
    assert session.run(f"/write {target}")
    assert target.read_bytes().startswith(b"\x89PNG")


def test_settings_commands(session):
    assert session.run("/headers off") and not session.settings.headers
    assert session.run("/theme nebula") and session.theme.name == "nebula"
    assert not session.run("/theme nope")
    assert session.run("/mode vi") and session.settings.editing_mode == "vi"
    assert session.run("/help") and session.run("/project") and session.run("/aliases")
    assert session.run("/exit") and session.exit_requested


def test_alias_with_fields(session):
    session.run("/alias login POST :8000/login username={user} password={password}")
    assert session.run("/login arthur 1234")
    assert json.loads(session.last.response.text)["body"] == {"username": "arthur", "password": "1234"}

    session.run("/alias create_user POST api.dev/users")
    assert session.run("/create_user name=ada age:=36")  # fields appended to an alias without placeholders
    assert json.loads(session.last.response.text)["body"] == {"name": "ada", "age": 36}
