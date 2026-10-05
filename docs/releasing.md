# Releasing

flare is published to PyPI as **`flare-http`** (the name `flare` was already taken); the installed command is `flare`.

Releases are built and uploaded by GitHub Actions (`.github/workflows/release.yml`) using PyPI **trusted publishing**, so no API token is stored anywhere.

## One-time setup

1. Create an account on [pypi.org](https://pypi.org/account/register/) and enable two-factor authentication.
2. Go to **Your account → Publishing → Add a new pending publisher** and fill in:
   - PyPI project name: `flare-http`
   - Owner: `arthurdaquinosilva`
   - Repository name: `flare`
   - Workflow name: `release.yml`
   - Environment name: `pypi`
3. On GitHub, open **Settings → Environments → New environment**, name it `pypi`. Optionally add yourself as a required reviewer so every upload needs a click.

The first successful release creates the project on PyPI and turns the pending publisher into a normal one.

## Cutting a release

1. Bump `version` in `pyproject.toml` and `__version__` in `src/flare/__init__.py`.
2. Add the changes to `CHANGELOG.md`.
3. Check the build locally:

   ```sh
   rm -rf dist && python -m build && python -m twine check --strict dist/*
   ```

4. Commit, push, then create a GitHub release with a `vX.Y.Z` tag:

   ```sh
   gh release create v0.1.0 --title "v0.1.0" --notes-file <(awk '/^## /{n++} n==1' CHANGELOG.md)
   ```

Publishing the release runs the workflow, which builds the sdist and wheel, checks them, and uploads to PyPI. Afterwards:

```sh
pipx install flare-http   # or: pip install flare-http
```

## Trying a release first (optional)

To rehearse on [TestPyPI](https://test.pypi.org), add a pending publisher there too and upload manually with a TestPyPI token:

```sh
python -m twine upload --repository testpypi dist/*
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ flare-http
```
