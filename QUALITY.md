# Quality and Release

Runner includes an automated quality gate for local development and releases.

## Run the quality gate

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
./scripts/quality_check.sh
```

The check covers:

- Python syntax
- Unit and integration tests
- Shell syntax
- ShellCheck when available
- Required project files
- CLI smoke tests
- Dependency sanity for graphics/export support

`ResourceWarning` messages from third-party libraries do not fail the gate unless a test itself fails.

## Release

```bash
make release
```

The release script runs the quality gate, creates a clean ZIP, strips local state and generated data, clears the Discord webhook URL, and verifies ZIP integrity.
