# Runner Tournament Platform

ChatGPT has been utilized in this project.

Runner is a local tournament manager and analytics platform for RoboCup 2D matches. It handles team validation, tournament execution, match result storage, RCG/RCL parsing, analytics, replay and web visualization, reports, Discord notifications, simulation utilities, and an optional plugin system.

[فارسی](README-Fa.md) · [Quality & Release](QUALITY.md) · [Plugin API](docs/PLUGIN_API.md)

## Features

- Round-robin and stepladder tournaments
- Team validation and tournament state stored in SQLite
- RCG world-state and RCL action parsing
- Match events, player frames, spatial metrics, possession, passing and shooting data
- Reproducible match and team analytics
- Advanced offline analytics and statistical simulation tools
- Local web dashboard with match replay, visual analytics and report downloads
- Match and tournament export to JSON, HTML, CSV, PDF and graphics archives
- Discord notifications with notification history stored in SQLite
- Optional Python plugins for events, completed matches and completed tournaments
- Automated quality checks and clean release packaging

## Requirements

- Linux with Bash
- Python 3.11+ (the current test environment uses Python 3.14)
- RoboCup 2D `rcssserver` and team binaries for real tournaments
- Python dependencies from `requirements.txt` for analytics, graphics and exports

## Installation

```bash
cd Runner
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
chmod +x run.sh scripts/quality_check.sh
```

For systems where Runner should install its dependencies directly:

```bash
./install_requirements.sh
```

## Configuration

The main configuration file is `config.conf`. Important options include:

| Option | Description |
|---|---|
| `type` | `round_robin` or `stepladder` |
| `fullstate` | Enable fullstate server mode |
| `synch_mode` | Enable synchronized server mode |
| `nr_extra_halfs` | Extra halves for stepladder matches |
| `penalty_shoot_outs` | Enable penalty shootouts when supported by the tournament setup |
| `data_collection` | Store parsed match data |
| `analytics_enabled` | Run analytics after ingestion |
| `spatial_grid_x`, `spatial_grid_y` | Spatial analysis resolution |
| `discord_enabled` | Enable Discord notifications |
| `discord_webhook_url` | Discord webhook URL; environment variable takes precedence |
| `notify_match_finished` | Notify after a match |
| `notify_tournament_finished` | Notify after a tournament |
| `plugins_enabled` | Allow configured plugin hooks to run automatically |
| `plugins_dir` | Plugin directory |

Keep the real Discord webhook out of Git. Prefer:

```bash
export RUNNER_DISCORD_WEBHOOK_URL='https://discord.com/api/webhooks/...'
```

## Teams

Teams are listed in `teams.txt`, one team name per line. A corresponding team directory is expected under `Bins/` and must pass Runner validation.

Example:

```text
TeamA
TeamB
TeamC
TeamD
```

## Running tournaments

Interactive launcher:

```bash
./run.sh
```

Or use the CLI directly:

```bash
python3 runner.py validate
python3 runner.py begin
python3 runner.py run --type round_robin
python3 runner.py run --type stepladder
```

The shell tournament scripts remain useful for the complete match workflow because they manage the RoboCup server, team processes, log files and post-match ingestion.

## Command line reference

### Tournament and match lifecycle

```bash
python3 runner.py validate
python3 runner.py begin
python3 runner.py start-match TeamA TeamB 1
python3 runner.py finish-match-rcg 1 --rcg-file ./match.rcg
python3 runner.py finish-match 1 2 1 TeamA
python3 runner.py finish-tournament completed
```

### Match data and analytics

```bash
python3 runner.py ingest-match 1 --rcg-file ./match.rcg --rcl-file ./match.rcl
python3 runner.py analyze-match 1
python3 runner.py analyze-advanced 1
```

### Simulation utilities

```bash
python3 runner.py simulate TOURNAMENT_ID --runs 10000 --seed 42
python3 runner.py benchmark TeamA TeamB --tournament-id TOURNAMENT_ID
python3 runner.py seed TOURNAMENT_ID
python3 runner.py ratings TOURNAMENT_ID
```

### Reports

```bash
python3 runner.py export-match 1 --format html
python3 runner.py export-match 1 --format pdf
python3 runner.py export-match 1 --format graphics
python3 runner.py export-tournament TOURNAMENT_ID --format pdf
```

### Web dashboard

```bash
python3 runner.py web
```

Then open `http://127.0.0.1:8000`. The dashboard provides tournament summaries, match details, replay, analytics visualizations, report downloads and notification history.

### Notifications

```bash
python3 runner.py notifications --limit 50
```

Discord notifications are generated in a separate process and recorded as `pending`, `sent` or `failed` in SQLite so a notification failure does not become a tournament failure.

## Plugins

Plugins are optional Python modules placed in the directory configured by `plugins_dir`. They are disabled by default for safety.

A plugin declares metadata and one or more hooks:

```python
PLUGIN = {
    "name": "my-plugin",
    "version": "1.0.0",
    "description": "Example integration",
    "hooks": ["on_match_finished"],
}

def on_match_finished(context):
    print(f"Match {context['match_id']} finished")
    return {"ok": True}
```

Supported hooks are `on_event`, `on_match_finished`, and `on_tournament_finished`. Plugin failures are isolated and logged; they do not terminate Runner.

Useful commands:

```bash
python3 runner.py plugins list
python3 runner.py plugins info my-plugin
python3 runner.py plugins run on_match_finished --payload '{"match_id": 1}'
```

See [docs/PLUGIN_API.md](docs/PLUGIN_API.md) for the full contract and examples.

## Data and output

Important runtime paths:

- `runner.db` — SQLite state and analytics
- `tournaments/` — tournament-specific match data and outputs
- `logs/` — Runner logs
- `reports/` — generated report files
- `plugins/` — optional local plugins
- `dist/` — release archives

Generated match files such as `.rcg` and `.rcl` are intentionally excluded from release archives.

## Quality and release

Run the complete quality gate before distributing Runner:

```bash
./scripts/quality_check.sh
```

Create a clean release with:

```bash
make release
```

The release process removes local databases, logs, match logs, generated reports and credentials, then checks ZIP integrity.

## Troubleshooting

### `matplotlib` or graphics export errors

Recreate the virtual environment and reinstall dependencies:

```bash
rm -rf .venv
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### Discord does not send

Check `discord_enabled`, the webhook URL, and notification permissions. Then inspect:

```bash
python3 runner.py notifications --limit 50
```

### A team fails validation

Run:

```bash
python3 runner.py validate
```

The command reports the exact team and validation error.

## Project layout

```text
Runner/
├── Analyzer/          # Report graphics and legacy analysis helpers
├── Bins/              # Team directories/binaries
├── core/              # Tournament, database, parsing, analytics, reports, plugins
├── docs/              # Developer and integration documentation
├── plugins/           # Optional drop-in plugins
├── scripts/           # Quality and release tooling
├── tests/             # Unit and integration tests
├── web/               # Local dashboard and static UI
├── config.conf        # Runtime configuration
├── teams.txt          # Team list
├── runner.py          # Main CLI
└── run.sh             # Interactive launcher
```

## Authors

- [Soroush Mazloum](https://github.com/SoroushMazloum)
- [Saleh Hamrahi](https://github.com/SalehHamrahi)

## License

See [LICENSE](LICENSE) before using or distributing this project.
