import pytest

from flare.request import ParseError, is_complete, parse


def test_curl_command():
    spec = parse("curl -X GET https://someendpoint.com/users/")
    assert (spec.method, spec.url) == ("GET", "https://someendpoint.com/users/")


def test_short_form_and_scheme_defaults():
    assert parse("GET api.dev/users").url == "https://api.dev/users"
    assert parse("get localhost:3000/x").url == "http://localhost:3000/x"
    assert parse("DELETE :8000/users/1").url == "http://localhost:8000/users/1"
    assert parse("api.dev").method == "GET"


def test_data_implies_post_and_json_body_is_json():
    spec = parse("""curl api.dev/users -d '{"name": "ada"}'""")
    assert spec.method == "POST"
    assert spec.header("content-type") == "application/json"
    assert parse("curl api.dev -d a=1 -d b=2").data == "a=1&b=2"
    assert parse("curl api.dev -d a=1").header("Content-Type") == "application/x-www-form-urlencoded"


def test_headers_flags_and_bundled_options():
    spec = parse("curl -sSLk -XPUT --header='Accept: text/plain' -H 'X-Id: 7' -u ada:pw -m 5 api.dev")
    assert spec.method == "PUT"
    assert spec.follow_redirects and not spec.verify
    assert spec.headers == [("Accept", "text/plain"), ("X-Id", "7")]
    assert spec.auth == ("ada", "pw")
    assert spec.timeout == 5


def test_get_moves_data_to_query_and_head():
    assert parse("curl -G api.dev/search -d q=x").url == "https://api.dev/search?q=x"
    assert parse("curl -I api.dev").method == "HEAD"


def test_env_vars_and_line_continuations():
    spec = parse("curl api.dev \\\n  -H 'Authorization: Bearer $TOKEN'", env={"TOKEN": "abc"})
    assert spec.header("Authorization") == "Bearer abc"
    with pytest.raises(ParseError, match=r"\$TOKEN is not set"):
        parse("curl api.dev/${TOKEN}", env={})


@pytest.mark.parametrize("text, message", [
    ("curl", "nothing to send"),
    ("curl -H 'X: 1'", "missing URL"),
    ("curl api.dev --bogus", "unknown option"),
    ("curl api.dev -F a=b", "not supported"),
    ("curl api.dev -H nocolon", "bad header"),
    ("curl a.dev b.dev", "unexpected argument"),
])
def test_errors(text, message):
    with pytest.raises(ParseError, match=message):
        parse(text, env={})


def test_is_complete():
    assert is_complete("GET api.dev")
    assert not is_complete("curl api.dev \\")
    assert not is_complete("curl api.dev -d '{")
