# Runner Plugin API

Runner plugins are small Python modules that extend the platform without changing core files. Plugins are loaded from `plugins_dir` and are disabled for automatic lifecycle hooks unless `plugins_enabled=true`.

## File format

A plugin is a `.py` file with a `PLUGIN` dictionary. Files beginning with `_` and `__init__.py` are ignored.

```python
PLUGIN = {
    "name": "discord-audit",
    "version": "1.0.0",
    "description": "Example integration",
    "hooks": ["on_match_finished"],
}

def on_match_finished(context):
    return {"ok": True, "match_id": context.get("match_id")}
```

Required metadata:

- `name`: unique human-readable name
- `version`: plugin version
- `description`: short description
- `hooks`: one or more supported hooks

## Hooks

### `on_event`

Runs after a Runner event is recorded. Context contains:

```text
tournament_id
match_id
db_path
level
message
context
```

### `on_match_finished`

Runs after a match is stored as completed. Depending on the finish path, context can contain:

```text
tournament_id
match_id
db_path
winner
score1
score2
```

The exact context is intentionally additive; plugins should read only fields they need.

### `on_tournament_finished`

Runs when a tournament is marked `completed`. Context contains:

```text
tournament_id
db_path
status
```

## Error isolation

Plugin discovery and hook execution are isolated from the Runner process. A malformed plugin is skipped. A plugin exception is logged and reported in the hook result. Plugin errors do not terminate a tournament.

## Security

A plugin is arbitrary Python code running with the same OS permissions as Runner. Only enable plugins you trust. Keep `plugins_enabled=false` unless you intentionally want lifecycle hooks.

## Manual execution

List plugins:

```bash
python3 runner.py plugins list
```

Inspect one plugin:

```bash
python3 runner.py plugins info discord-audit
```

Run a hook manually:

```bash
python3 runner.py plugins run on_match_finished --payload '{"match_id": 12}'
```

Manual execution does not require `plugins_enabled=true`; the flag controls automatic lifecycle hooks only.
