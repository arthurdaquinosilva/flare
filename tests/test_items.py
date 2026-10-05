import json

import pytest

from flare.request import ParseError, parse


def test_fields_become_a_json_body():
    spec = parse("POST http://localhost:8000/login username='arthur' password='1234'")
    assert spec.method == "POST"
    assert json.loads(spec.data) == {"username": "arthur", "password": "1234"}
    assert spec.header("Content-Type") == "application/json"


def test_fields_imply_post():
    assert parse(":8000/login user=ada").method == "POST"


def test_raw_json_query_and_header_items():
    spec = parse("""PUT api.dev/u age:=33 admin:=true tags:='["a"]' note=a:b=c page==2 X-Token:abc""", env={})
    assert json.loads(spec.data) == {"age": 33, "admin": True, "tags": ["a"], "note": "a:b=c"}
    assert spec.url == "https://api.dev/u?page=2"
    assert spec.header("X-Token") == "abc"


def test_query_only_stays_get():
    spec = parse("api.dev/search q=='hello world'")
    assert (spec.method, spec.url, spec.data) == ("GET", "https://api.dev/search?q=hello+world", None)


def test_items_expand_env_vars():
    assert json.loads(parse("POST a.dev password=$PW", env={"PW": "x"}).data) == {"password": "x"}


@pytest.mark.parametrize("text, message", [
    ("POST a.dev n:=nope", "expects JSON"),
    ("POST a.dev a=1 -d b=2", "not both"),
    ("POST a.dev stray", "fields look like key=value"),
])
def test_item_errors(text, message):
    with pytest.raises(ParseError, match=message):
        parse(text, env={})
