# Changelog

## Unreleased

- **pitch**, one palette shared by ember, shtick, cinder, flare and lore: cool blue/violet hues on the terminal's own black. Backgrounds stay transparent, completion menus included (the current item is bold instead of shaded). flare's accent is yellow, and the `://flare` wordmark follows it. The `void`, `nebula` and `matrix` themes are gone; a config that still names one falls back to pitch with a warning.

## 0.2.0

- **A new look**, in querky's style: the input sits between two horizontal rules, with a one-line footer under them instead of the filled bar, key bar and mode line — `-- INSERT --` in vi mode or `? for shortcuts` on the left, the project, its aliases and the last status on the right. `?` on an empty prompt lists the shortcuts, and completions are a plain list under the prompt.
- **Responses without a rail**: every input is echoed as `> …`, and what it printed hangs under a `⎿` marker, five columns in — the response, then its status line (`✓ 200 OK · 12ms · 288 B · json`). Command output (`/aliases`, `/help`, …) hangs under its input the same way. The spinner reads `✻ GET host… (1.2s · ctrl+c to cancel)`.
- Ctrl+C on an empty prompt now exits on a second press within 1.5 seconds; Ctrl+D still exits.

## 0.1.0

First release.

- Send requests as curl commands or `METHOD url`, with httpie-style fields: `key=value`, `key:=json`, `key==query`, `Header:value`.
- Responses on a rail: status, headers and a re-indented, highlighted body (JSON, HTML, XML, YAML…), with status, time, size and type in the footer.
- Per-project aliases (`/alias`, `/save`, `/aliases`, `/edit`, `/unalias`) with `{placeholders}`; `$VARS` stay unexpanded when saved.
- ember's interface: pixel wordmark, filled input bar, key bar, vi or emacs keys, history, completion, three themes.
- One-shot mode: `flare GET url`, `flare /alias`; piped output is the bare body.
