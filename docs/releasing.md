# Releasing

flare is published only on GitHub — it isn't on PyPI. People install it with `install.sh`, which downloads the source archive of a branch or tag from GitHub and pip-installs it into its own virtual environment.

## Cutting a release

1. Bump `version` in `pyproject.toml` and `__version__` in `src/flare/__init__.py`.
2. Add the changes to `CHANGELOG.md`.
3. Check that it builds:

   ```sh
   rm -rf dist && python -m build
   ```

4. Commit, push, then create a GitHub release with a `vX.Y.Z` tag:

   ```sh
   gh release create v0.1.0 --title "v0.1.0" --notes-file <(awk '/^## /{n++} n==1' CHANGELOG.md)
   ```

The tag is what `install.sh` installs when asked for that version:

```sh
curl -fsSL https://raw.githubusercontent.com/arthurdaquinosilva/flare/main/install.sh | sh -s -- 0.1.0
```

`install.sh` is served straight from `main` and installs `main` unless given a version, so it needs no change per release. Keep it working on plain `sh` (dash): `tests/test_install.py` runs it through `sh -n` and shellcheck.
