# flare

**A calm, beautiful terminal client for HTTP requests.** ember's look — the pixel wordmark, filled input bar, key bar and vi mode line — built around sending requests and reading responses.

- **Paste curl, or don't.** `curl -X GET https://api.dev/users` works as-is, and so does `GET api.dev/users`.
- **Readable responses.** Status, headers and a re-indented, highlighted body (JSON, HTML, XML, YAML…) on a rail, with a footer for status, time, size and type.
- **Aliases per project.** `/alias get_all_users GET api.dev/users`, then just `/get_all_users`. Each git repository has its own aliases.
- **Keys you know.** vi or emacs bindings, history with search, completion for commands, aliases, methods and flags.

## Install

```sh
pipx install flare-http    # the `flare` command everywhere, isolated from your projects
pip install flare-http     # or into the current environment
```

The package is `flare-http` on PyPI (`flare` was taken); the command is `flare`. Requires Python 3.10+ on macOS or Linux.

## Quick tour

```text
> curl -X GET https://someendpoint.com/users/        paste any curl command
> GET api.dev/users                                  or a method and a URL (https assumed)
> POST :8000/login username='arthur' password='1234'  fields after the URL become a JSON body
> PUT :8000/users/1 age:=33 admin:=true              := sends raw JSON (numbers, booleans, lists…)
> GET api.dev/search q=='hello world' X-Token:abc    == adds a query parameter, Name:value a header
> POST :8000/users -d '{"name": "ada"}'              :port means localhost; -d JSON bodies go as JSON
> GET api.dev/me -H 'Authorization: Bearer $TOKEN'   $VARS come from your environment

> /alias get_all_users curl -X GET https://someendpoint.com/users/
> /get_all_users
> /alias get_user GET api.dev/users/{id}             {placeholders} are filled when called
> /get_user 42                                       or /get_user id=42; extra args are appended (-v, -H …)
> /alias create_user POST api.dev/users
> /create_user name=ada age:=36                      so fields can be passed to an alias too
> /save health                                       save the last request as /health
> /aliases                                           list this project's aliases
```

| Command | |
| --- | --- |
| `/alias <name> <request>` | save a request (`/alias <name>` shows it) |
| `/save <name>` | save the last request |
| `/aliases` · `/unalias <name>` · `/edit <name>` | list · delete · load into the input to change |
| `/body` · `/write <file>` | read the whole last response in a pager · save its body |
| `/headers [on\|off]` · `/theme <name>` · `/mode vi\|emacs` | display settings |
| `/project` · `/clear` · `/help` · `/exit` | |

Supported curl options: `-X -H -d --data-raw --data-binary --data-urlencode --json -u -A -e -b -m -L -k -I -G -v --url`. Cosmetic ones (`-s -S -i -f --compressed`…) are accepted and ignored. Multipart forms (`-F`) aren't supported yet.

## Projects

A project is the git repository you're in, or the current directory outside one (`--project DIR` picks another). Its aliases and input history live in `~/.local/share/flare/projects/<name>-<hash>/`, never inside the repo. `/project` shows where. Aliases are stored exactly as typed, so `$TOKEN` stays a reference rather than becoming a saved secret.

## Command line

```sh
flare                              # interactive
flare --vi --theme nebula          # vi keys, another theme (void, nebula, matrix)
flare GET api.dev/users            # send one request and exit (status 1 on errors or 4xx/5xx)
flare /get_all_users | jq .        # piped output is the bare response body
```

## Configuration

`~/.config/flare/config.toml`:

```toml
theme = "void"         # void, nebula, matrix
editing_mode = "vi"    # or emacs
headers = true         # show response headers
timeout = 30           # seconds
max_lines = 300        # longer bodies are cut; /body shows everything
```

## Development

Releases go to PyPI from GitHub; see [docs/releasing.md](https://github.com/arthurdaquinosilva/flare/blob/main/docs/releasing.md).

```sh
python -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest
docker build -t flare . && docker run --rm flare     # lint + tests in a container
```
