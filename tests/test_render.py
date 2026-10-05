import httpx

from flare.render import body_kind, format_duration, format_size, pretty_body


def resp(content, ctype=None):
    headers = {"Content-Type": ctype} if ctype else {}
    return httpx.Response(200, content=content, headers=headers)


def test_body_detection():
    assert body_kind(resp(b"")) == ("empty", "")
    assert body_kind(resp(b'{"a":1}', "application/vnd.api+json")) == ("text", "json")
    assert body_kind(resp(b'[1, 2]')) == ("text", "json")  # sniffed without a content type
    assert body_kind(resp(b"<!DOCTYPE html><p>x")) == ("text", "html")
    assert body_kind(resp(b"\x89PNG", "image/png"))[0] == "binary"
    assert body_kind(resp(b"hello", "text/plain")) == ("text", "text")


def test_json_is_reindented():
    text, lexer = pretty_body(resp('{"name":"ação","n":[1,2]}'.encode(), "application/json"))
    assert lexer == "json"
    assert text == '{\n  "name": "ação",\n  "n": [\n    1,\n    2\n  ]\n}'


def test_units():
    assert format_size(512) == "512 B"
    assert format_size(2048) == "2.0 KB"
    assert format_duration(0.1234) == "123ms"
    assert format_duration(2.5) == "2.50s"
