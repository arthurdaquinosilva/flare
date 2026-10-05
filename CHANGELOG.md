# Changelog

## 0.1.0

First release.

- Send requests as curl commands or `METHOD url`, with httpie-style fields: `key=value`, `key:=json`, `key==query`, `Header:value`.
- Responses on a rail: status, headers and a re-indented, highlighted body (JSON, HTML, XML, YAML…), with status, time, size and type in the footer.
- Per-project aliases (`/alias`, `/save`, `/aliases`, `/edit`, `/unalias`) with `{placeholders}`; `$VARS` stay unexpanded when saved.
- ember's interface: pixel wordmark, filled input bar, key bar, vi or emacs keys, history, completion, three themes.
- One-shot mode: `flare GET url`, `flare /alias`; piped output is the bare body.
