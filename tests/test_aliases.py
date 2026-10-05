import pytest

from flare.project import AliasError, AliasStore, Project, expand


def test_aliases_persist_per_project(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    for root in (a, b):
        (root / ".git").mkdir(parents=True)
    (a / "sub" / "dir").mkdir(parents=True)
    base = tmp_path / "data"

    store = AliasStore(Project.locate(a / "sub" / "dir", base=base))  # found from inside the repo
    store.set("get_all_users", "curl -X GET https://someendpoint.com/users/")

    assert AliasStore(Project.locate(a, base=base)).get("/get_all_users") == "curl -X GET https://someendpoint.com/users/"
    assert AliasStore(Project.locate(b, base=base)).get("get_all_users") is None


def test_alias_names_are_checked(project):
    store = AliasStore(project)
    with pytest.raises(AliasError, match="bad alias name"):
        store.set("has space", "GET a.dev")
    with pytest.raises(AliasError, match="built-in"):
        store.set("help", "GET a.dev", reserved=("help",))
    with pytest.raises(AliasError, match="no alias"):
        store.remove("nope")


def test_placeholders():
    cmd = "GET api.dev/users/{id}/posts/{post}"
    assert expand(cmd, ["1", "2"]) == "GET api.dev/users/1/posts/2"
    assert expand(cmd, ["post=9", "1"]) == "GET api.dev/users/1/posts/9"
    assert expand("GET api.dev/users", ["-v", "-H", "X-A: 1"]) == "GET api.dev/users -v -H 'X-A: 1'"
    with pytest.raises(AliasError, match=r"missing \{post\}"):
        expand(cmd, ["1"])
