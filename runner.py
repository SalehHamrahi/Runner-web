#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VERSION_FILE = ROOT / "VERSION"
VERSION = VERSION_FILE.read_text(encoding="utf-8").strip() if VERSION_FILE.exists() else "dev"


def ensure_project_venv() -> None:
    """Re-exec this script with the project virtualenv interpreter.

    Python cannot source a shell activation script into its parent shell.
    Re-executing with .venv/bin/python gives the same practical result for
    the Runner process and, importantly, happens before project imports.
    """
    if os.environ.get("RUNNER_VENV_ACTIVE") == "1":
        return

    if sys.prefix != sys.base_prefix:
        return

    venv_python = ROOT / ".venv" / "bin" / "python"
    if not venv_python.exists():
        return

    if Path(sys.executable).resolve() == venv_python.resolve():
        return

    env = os.environ.copy()
    env["RUNNER_VENV_ACTIVE"] = "1"
    print(f"\033[36m[Runner]\033[0m Using virtual environment: {venv_python}")
    os.execve(str(venv_python), [str(venv_python), *sys.argv], env)


ensure_project_venv()

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import RunnerConfig
from core.database import RunnerDB
from core.logger import configure
from core.tournament import create_tournament, utc_now
from core.validation import validate_teams
from core.match_ingestion import ingest_match_data
from core.analytics import analyze_match
from core.advanced_analytics import analyze_advanced
from core.simulation import simulate_round_robin, benchmark, auto_seed, elo_ratings
from web.server import serve as serve_web
from core.notifications import dispatch_async, list_history
from core.plugins import plugin_details, plugin_summary, run_hook


def read_teams(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"Teams file not found: {path}")
    teams = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            teams.append(line)
    return teams


def env_path(name: str, default: Path) -> Path:
    return Path(os.environ.get(name, str(default)))


def setup_logging(config: RunnerConfig) -> None:
    log_dir = env_path("RUNNER_LOG_DIR", ROOT / "logs")
    configure(log_dir, config.log_level)


def cmd_validate(args: argparse.Namespace) -> int:
    config = RunnerConfig.load(ROOT / "config.conf")
    setup_logging(config)
    teams = read_teams(ROOT / "teams.txt")
    if not teams:
        print("No teams found in teams.txt", file=sys.stderr)
        return 1

    results = validate_teams(ROOT, teams)
    all_valid = True
    for result in results:
        marker = "OK" if result.valid else "ERROR"
        color = "\033[32m" if result.valid else "\033[31m"
        print(f"{color}[{marker}]\033[0m {result.name}: {result.message}")
        if not result.valid:
            all_valid = False

    return 0 if all_valid else 1


def cmd_begin(args: argparse.Namespace) -> int:
    config = RunnerConfig.load(ROOT / "config.conf")
    setup_logging(config)
    teams = read_teams(ROOT / "teams.txt")
    if not teams:
        print("teams.txt is empty", file=sys.stderr)
        return 1

    validations = validate_teams(ROOT, teams)
    invalid = [item for item in validations if not item.valid]
    if invalid:
        print("Team validation failed:", file=sys.stderr)
        for item in invalid:
            print(f"  - {item.name}: {item.message}", file=sys.stderr)
        return 1

    tournament_id, tournament_dir, db = create_tournament(ROOT, config, teams)
    try:
        started = utc_now()
        db.update_tournament_status(tournament_id, "running", started, "started_at")
        for item in validations:
            db.register_team(
                tournament_id,
                item.name,
                str(item.directory.relative_to(ROOT)),
                str(item.start_script.relative_to(ROOT)) if item.start_script else None,
                item.valid,
                item.message,
            )
    finally:
        db.close()

    print(tournament_id)
    return 0


def db_for_env() -> RunnerDB:
    return RunnerDB(env_path("RUNNER_DB", ROOT / "runner.db"))


def cmd_start_match(args: argparse.Namespace) -> int:
    tournament_id = os.environ.get("RUNNER_TOURNAMENT_ID")
    if not tournament_id:
        print("RUNNER_TOURNAMENT_ID is not set", file=sys.stderr)
        return 1
    config = RunnerConfig.load(ROOT / "config.conf")
    setup_logging(config)
    db = db_for_env()
    try:
        match_id = db.start_match(
            tournament_id,
            args.team1,
            args.team2,
            args.match_number,
            utc_now(),
        )
    finally:
        db.close()
    print(match_id)
    return 0


def cmd_record_event(args: argparse.Namespace) -> int:
    tournament_id = os.environ.get("RUNNER_TOURNAMENT_ID")
    if not tournament_id:
        print("RUNNER_TOURNAMENT_ID is not set", file=sys.stderr)
        return 1
    config = RunnerConfig.load(ROOT / "config.conf")
    setup_logging(config)
    db = db_for_env()
    try:
        context = json.loads(args.context) if args.context else None
        db.record_event(tournament_id, args.level, args.message, utc_now(), args.match_id, context)
        if config.plugins_enabled:
            run_hook(_plugins_root(config), "on_event", {
                "tournament_id": tournament_id,
                "match_id": args.match_id,
                "db_path": str(db.path),
                "level": args.level,
                "message": args.message,
                "context": context or {},
            })
        if args.notify_type:
            dispatch_async(
                ROOT / "config.conf",
                db.path,
                args.notify_type,
                tournament_id,
                args.match_id,
                {
                    "title": args.message,
                    "description": args.message,
                    "fields": [("Level", args.level)],
                },
            )
    finally:
        db.close()
    return 0


def cmd_ingest_match(args: argparse.Namespace) -> int:
    tournament_id = os.environ.get("RUNNER_TOURNAMENT_ID")
    if not tournament_id:
        print("RUNNER_TOURNAMENT_ID is not set", file=sys.stderr)
        return 1
    config = RunnerConfig.load(ROOT / "config.conf")
    setup_logging(config)
    db = db_for_env()
    try:
        match = db.get_match(args.match_id)
        if match is None:
            print(f"Match {args.match_id} not found", file=sys.stderr)
            return 1
        rcg_file = Path(args.rcg_file).resolve() if args.rcg_file else None
        if rcg_file is None or not rcg_file.exists():
            print("RCG file not found", file=sys.stderr)
            return 1
        output_dir = Path(os.environ.get("RUNNER_TOURNAMENT_DIR", str(ROOT / "tournaments" / tournament_id))) / "matches" / f"match_{match['match_number']}_data"
        rcl_file = Path(args.rcl_file).resolve() if args.rcl_file else rcg_file.with_suffix('.rcl')
        if not rcl_file.exists():
            rcl_file = None
        summary = ingest_match_data(db, args.match_id, rcg_file, output_dir, match['team1'], match['team2'], config.spatial_grid_x, config.spatial_grid_y, rcl_file, config.analytics_enabled)
        print(json.dumps(summary, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(f"Match data ingestion failed: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


def cmd_analyze_match(args: argparse.Namespace) -> int:
    tournament_id = os.environ.get("RUNNER_TOURNAMENT_ID")
    if not tournament_id:
        print("RUNNER_TOURNAMENT_ID is not set", file=sys.stderr)
        return 1
    config = RunnerConfig.load(ROOT / "config.conf")
    setup_logging(config)
    db = db_for_env()
    try:
        match = db.get_match(args.match_id)
        if match is None:
            print(f"Match {args.match_id} not found", file=sys.stderr)
            return 1
        tournament_dir = Path(os.environ.get("RUNNER_TOURNAMENT_DIR", str(ROOT / "tournaments" / tournament_id)))
        output_dir = tournament_dir / "matches" / f"match_{match['match_number']}_data" / "analytics"
        summary = analyze_match(db, args.match_id, output_dir)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f"Match analysis failed: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


def cmd_analyze_advanced(args: argparse.Namespace) -> int:
    tournament_id = os.environ.get("RUNNER_TOURNAMENT_ID")
    if not tournament_id:
        print("RUNNER_TOURNAMENT_ID is not set", file=sys.stderr)
        return 1
    config = RunnerConfig.load(ROOT / "config.conf")
    setup_logging(config)
    db = db_for_env()
    try:
        data = analyze_advanced(db, args.match_id)
        tournament_dir = Path(os.environ.get("RUNNER_TOURNAMENT_DIR", str(ROOT / "tournaments" / tournament_id)))
        match = db.get_match(args.match_id)
        if match:
            out = tournament_dir / "matches" / f"match_{match['match_number']}_data" / "analytics"
            out.mkdir(parents=True, exist_ok=True)
            (out / "advanced_analytics.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f"Advanced analysis failed: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()

def cmd_finish_tournament(args: argparse.Namespace) -> int:
    tournament_id = os.environ.get("RUNNER_TOURNAMENT_ID")
    if not tournament_id:
        print("RUNNER_TOURNAMENT_ID is not set", file=sys.stderr)
        return 1
    config = RunnerConfig.load(ROOT / "config.conf")
    setup_logging(config)
    db = db_for_env()
    try:
        db.update_tournament_status(tournament_id, args.status, utc_now(), "finished_at")
        db.record_event(tournament_id, "INFO", f"Tournament {tournament_id} status: {args.status}", utc_now())
        if args.status == "completed":
            dispatch_async(
                ROOT / "config.conf",
                db.path,
                "tournament_finished",
                tournament_id,
                payload={
                    "title": "🏆 Tournament Finished",
                    "description": f"Tournament `{tournament_id}` completed successfully.",
                    "fields": [("Tournament", tournament_id)],
                },
            )
            if config.plugins_enabled:
                run_hook(_plugins_root(config), "on_tournament_finished", {
                    "tournament_id": tournament_id,
                    "db_path": str(db.path),
                    "status": args.status,
                })
    finally:
        db.close()
    return 0


def _parse_rcg_result(rcg_file: Path) -> dict[str, object] | None:
    pattern = r'(\d{8}\d+)-(.+?)_(\d+)(?:_(\d+))?-vs-(.+?)_(\d+)(?:_(\d+))?\.rcg$'
    match = re.match(pattern, rcg_file.name)
    if not match:
        return None
    return {
        'team1': match.group(2),
        'score1': int(match.group(3)),
        'penalty1': int(match.group(4)) if match.group(4) else None,
        'team2': match.group(5),
        'score2': int(match.group(6)),
        'penalty2': int(match.group(7)) if match.group(7) else None,
    }


def _latest_rcg(root: Path) -> Path | None:
    files = list(root.glob('*.rcg'))
    if not files:
        return None
    return max(files, key=lambda path: path.stat().st_mtime_ns)


def cmd_finish_match_rcg(args: argparse.Namespace) -> int:
    tournament_id = os.environ.get('RUNNER_TOURNAMENT_ID')
    if not tournament_id:
        print('RUNNER_TOURNAMENT_ID is not set', file=sys.stderr)
        return 1

    config = RunnerConfig.load(ROOT / 'config.conf')
    setup_logging(config)
    db = db_for_env()
    try:
        match = db.get_match(args.match_id)
        if match is None:
            print(f'Match {args.match_id} not found', file=sys.stderr)
            return 1

        rcg_file = Path(args.rcg_file).resolve() if args.rcg_file else _latest_rcg(ROOT)
        if rcg_file is None or not rcg_file.exists():
            print('No RCG file found', file=sys.stderr)
            return 1

        result = _parse_rcg_result(rcg_file)
        if result is None:
            print(f'Could not parse match result from RCG filename: {rcg_file.name}', file=sys.stderr)
            return 1

        if result['team1'] != match['team1'] or result['team2'] != match['team2']:
            print(
                f"RCG teams do not match DB match: {result['team1']} vs {result['team2']} != {match['team1']} vs {match['team2']}",
                file=sys.stderr,
            )
            return 1

        winner = result['team1'] if result['score1'] > result['score2'] else result['team2'] if result['score2'] > result['score1'] else None
        if result['penalty1'] is not None and result['penalty2'] is not None:
            winner = result['team1'] if result['penalty1'] > result['penalty2'] else result['team2']
        elif winner is None:
            winner = result['team2'] if config.tournament_type == 'stepladder' else 'Draw (no penalties)'

        db.finish_match(
            args.match_id,
            int(result['score1']),
            int(result['score2']),
            winner,
            utc_now(),
            result['penalty1'],
            result['penalty2'],
            str(rcg_file),
            str(rcg_file.with_suffix('.rcl')) if rcg_file.with_suffix('.rcl').exists() else None,
        )
        db.record_event(
            tournament_id,
            'INFO',
            f"Match {args.match_id} finished: {match['team1']} {result['score1']} - {result['score2']} {match['team2']} -> {winner}",
            utc_now(),
            args.match_id,
        )
        dispatch_async(
            ROOT / 'config.conf',
            db.path,
            'match_finished',
            tournament_id,
            args.match_id,
            {'title': '⚽ Match Finished'},
        )
        if config.plugins_enabled:
            run_hook(_plugins_root(config), "on_match_finished", {
                "tournament_id": tournament_id,
                "match_id": args.match_id,
                "db_path": str(db.path),
                "winner": winner,
            })
        print(winner)
        return 0
    finally:
        db.close()


def cmd_finish(args: argparse.Namespace) -> int:
    # Compatibility helper used by scripts that already have parsed scores.
    tournament_id = os.environ.get("RUNNER_TOURNAMENT_ID")
    if not tournament_id:
        print("RUNNER_TOURNAMENT_ID is not set", file=sys.stderr)
        return 1
    config = RunnerConfig.load(ROOT / "config.conf")
    setup_logging(config)
    db = db_for_env()
    try:
        db.finish_match(
            args.match_id,
            args.score1,
            args.score2,
            args.winner,
            utc_now(),
            args.penalty1,
            args.penalty2,
            args.rcg_file,
            args.rcl_file,
        )
        db.record_event(
            tournament_id,
            "INFO",
            f"Match {args.match_id} finished: {args.winner}",
            utc_now(),
            args.match_id,
        )
        match = db.get_match(args.match_id)
        if match:
            dispatch_async(
                ROOT / "config.conf",
                db.path,
                "match_finished",
                tournament_id,
                args.match_id,
                {
                    "title": f"🏆 Match Finished — {args.winner}",
                    "description": f"{match['team1']} {args.score1} - {args.score2} {match['team2']}",
                    "fields": [
                        ("Winner", args.winner),
                        ("Match", str(args.match_id)),
                    ],
                },
            )
            if config.plugins_enabled:
                run_hook(_plugins_root(config), "on_match_finished", {
                    "tournament_id": tournament_id,
                    "match_id": args.match_id,
                    "db_path": str(db.path),
                    "winner": args.winner,
                    "score1": args.score1,
                    "score2": args.score2,
                })
    finally:
        db.close()
    return 0



def _store_simulation(db: RunnerDB, tournament_id: str | None, sim_type: str, runs: int, seed: int | None, parameters: dict, result: dict) -> None:
    db.conn.execute(
        "INSERT INTO simulation_runs(tournament_id, simulation_type, runs, seed, parameters_json, result_json) VALUES (?,?,?,?,?,?)",
        (tournament_id, sim_type, runs, seed, json.dumps(parameters, ensure_ascii=False), json.dumps(result, ensure_ascii=False)),
    )
    db.conn.commit()


def cmd_simulate(args: argparse.Namespace) -> int:
    config = RunnerConfig.load(ROOT / "config.conf")
    setup_logging(config)
    db = db_for_env()
    try:
        result = simulate_round_robin(db, args.tournament_id, args.runs, args.seed)
        _store_simulation(db, args.tournament_id, "round_robin_monte_carlo", args.runs, args.seed, {"format": "round_robin"}, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f"Simulation failed: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


def cmd_benchmark(args: argparse.Namespace) -> int:
    config = RunnerConfig.load(ROOT / "config.conf")
    setup_logging(config)
    db = db_for_env()
    try:
        result = benchmark(db, args.team1, args.team2, args.tournament_id, args.runs, args.seed)
        db.conn.execute(
            "INSERT INTO benchmark_runs(tournament_id, team1, team2, runs, seed, result_json) VALUES (?,?,?,?,?,?)",
            (args.tournament_id, args.team1, args.team2, args.runs, args.seed, json.dumps(result, ensure_ascii=False)),
        )
        db.conn.commit()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f"Benchmark failed: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


def cmd_seed(args: argparse.Namespace) -> int:
    config = RunnerConfig.load(ROOT / "config.conf")
    setup_logging(config)
    db = db_for_env()
    try:
        result = auto_seed(db, args.tournament_id)
        print(json.dumps({"tournament_id": args.tournament_id, "seeding": result}, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f"Seeding failed: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


def cmd_ratings(args: argparse.Namespace) -> int:
    config = RunnerConfig.load(ROOT / "config.conf")
    setup_logging(config)
    db = db_for_env()
    try:
        ratings = elo_ratings(db, args.tournament_id)
        print(json.dumps({"tournament_id": args.tournament_id, "ratings": ratings}, ensure_ascii=False, indent=2))
        return 0
    finally:
        db.close()

def cmd_export_match(args: argparse.Namespace) -> int:
    config = RunnerConfig.load(ROOT / "config.conf")
    setup_logging(config)
    db_path = env_path("RUNNER_DB", ROOT / "runner.db")
    output_root = env_path("RUNNER_REPORT_DIR", ROOT / "reports")
    try:
        path = export_match(db_path, args.match_id, args.format, output_root)
        print(path)
        return 0
    except Exception as exc:
        print(f"Match export failed: {exc}", file=sys.stderr)
        return 1


def cmd_export_tournament(args: argparse.Namespace) -> int:
    config = RunnerConfig.load(ROOT / "config.conf")
    setup_logging(config)
    db_path = env_path("RUNNER_DB", ROOT / "runner.db")
    output_root = env_path("RUNNER_REPORT_DIR", ROOT / "reports")
    try:
        path = export_tournament(db_path, args.tournament_id, args.format, output_root)
        print(path)
        return 0
    except Exception as exc:
        print(f"Tournament export failed: {exc}", file=sys.stderr)
        return 1


def cmd_notifications(args: argparse.Namespace) -> int:
    db = db_for_env()
    try:
        print(json.dumps(list_history(db, args.limit), ensure_ascii=False, indent=2))
        return 0
    finally:
        db.close()


def cmd_web(args: argparse.Namespace) -> int:
    config = RunnerConfig.load(ROOT / "config.conf")
    setup_logging(config)
    db_path = env_path("RUNNER_DB", ROOT / "runner.db")
    print(f"Starting Runner Web Dashboard on http://{args.host}:{args.port}")
    serve_web(db_path, args.host, args.port)
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    # Kept as a convenience entry point; run.sh remains the shell launcher.
    script = ROOT / ("Group_tournament.sh" if args.type == "round_robin" else "Stepladder_tournament.sh")
    env = os.environ.copy()
    env["RUNNER_ROOT"] = str(ROOT)
    subprocess.run([str(script)], cwd=ROOT, env=env, check=False)
    return 0


def _plugins_root(config: RunnerConfig | None = None) -> Path:
    if os.environ.get("RUNNER_PLUGINS_DIR"):
        return Path(os.environ["RUNNER_PLUGINS_DIR"])
    if config is not None:
        return ROOT / config.plugins_dir
    return ROOT / "plugins"


def cmd_plugins(args: argparse.Namespace) -> int:
    root = _plugins_root()
    if args.plugin_command == "list":
        print(json.dumps(plugin_summary(root), ensure_ascii=False, indent=2))
        return 0
    if args.plugin_command == "info":
        info = plugin_details(root, args.name)
        if info is None:
            print(f"Plugin not found: {args.name}", file=sys.stderr)
            return 1
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return 0
    if args.plugin_command == "run":
        try:
            context = json.loads(args.payload) if args.payload else {}
        except json.JSONDecodeError as exc:
            print(f"Invalid JSON payload: {exc}", file=sys.stderr)
            return 1
        results = run_hook(root, args.hook, context)
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0
    print("Unknown plugin command", file=sys.stderr)
    return 1



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Runner Tournament management CLI")
    parser.add_argument("--version", action="version", version=f"Runner {VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("validate", help="Validate all configured teams")
    sub.add_parser("begin", help="Create a new tournament and print its ID")

    p_start = sub.add_parser("start-match", help="Create a match record")
    p_start.add_argument("team1")
    p_start.add_argument("team2")
    p_start.add_argument("match_number", type=int)

    p_event = sub.add_parser("event", help="Record a tournament event")
    p_event.add_argument("level", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
    p_event.add_argument("message")
    p_event.add_argument("--match-id", type=int)
    p_event.add_argument("--context")
    p_event.add_argument("--notify-type", choices=["team_crash", "server_crash", "match_finished", "tournament_finished"])

    p_ingest = sub.add_parser("ingest-match", help="Extract match data from an RCG file")
    p_ingest.add_argument("match_id", type=int)
    p_ingest.add_argument("--rcg-file", required=True)
    p_ingest.add_argument("--rcl-file")

    p_analyze = sub.add_parser("analyze-match", help="Run analytics for a match")
    p_analyze.add_argument("match_id", type=int)

    p_advanced = sub.add_parser("analyze-advanced", help="Run advanced analytics for a match")
    p_advanced.add_argument("match_id", type=int)

    p_sim = sub.add_parser("simulate", help="Run a reproducible Monte Carlo round-robin simulation")
    p_sim.add_argument("tournament_id")
    p_sim.add_argument("--runs", type=int, default=10000)
    p_sim.add_argument("--seed", type=int, default=42)

    p_bench = sub.add_parser("benchmark", help="Benchmark two teams with Monte Carlo and historical head-to-head context")
    p_bench.add_argument("team1")
    p_bench.add_argument("team2")
    p_bench.add_argument("--tournament-id")
    p_bench.add_argument("--runs", type=int, default=10000)
    p_bench.add_argument("--seed", type=int, default=42)

    p_seed = sub.add_parser("seed", help="Generate Elo-based team seeding for a tournament")
    p_seed.add_argument("tournament_id")

    p_rating = sub.add_parser("ratings", help="Show Elo-style ratings for a tournament")
    p_rating.add_argument("tournament_id")

    p_export_match = sub.add_parser("export-match", help="Export a match report")
    p_export_match.add_argument("match_id", type=int)
    p_export_match.add_argument("--format", choices=["json", "html", "csv", "pdf", "graphics"], default="html")

    p_export_tournament = sub.add_parser("export-tournament", help="Export a tournament report")
    p_export_tournament.add_argument("tournament_id")
    p_export_tournament.add_argument("--format", choices=["json", "html", "csv", "pdf", "graphics"], default="html")

    p_notifications = sub.add_parser("notifications", help="Show Discord notification history")
    p_notifications.add_argument("--limit", type=int, default=50)

    p_plugins = sub.add_parser("plugins", help="Manage Runner plugins")
    plugins_sub = p_plugins.add_subparsers(dest="plugin_command", required=True)
    plugins_sub.add_parser("list", help="List discovered plugins")
    p_plugin_info = plugins_sub.add_parser("info", help="Show plugin metadata")
    p_plugin_info.add_argument("name")
    p_plugin_run = plugins_sub.add_parser("run", help="Run a plugin hook manually")
    p_plugin_run.add_argument("hook", choices=["on_event", "on_match_finished", "on_tournament_finished"])
    p_plugin_run.add_argument("--payload", default="{}", help="JSON context passed to the hook")

    p_web = sub.add_parser("web", help="Start the web analytics dashboard")
    p_web.add_argument("--host", default="127.0.0.1")
    p_web.add_argument("--port", type=int, default=8000)

    p_tournament_finish = sub.add_parser("finish-tournament", help="Set tournament final status")
    p_tournament_finish.add_argument("status", choices=["completed", "failed", "cancelled"])

    p_finish_rcg = sub.add_parser("finish-match-rcg", help="Finish a match using the latest RCG filename")
    p_finish_rcg.add_argument("match_id", type=int)
    p_finish_rcg.add_argument("--rcg-file")

    p_finish = sub.add_parser("finish-match", help="Finish a match record")
    p_finish.add_argument("match_id", type=int)
    p_finish.add_argument("score1", type=int)
    p_finish.add_argument("score2", type=int)
    p_finish.add_argument("winner")
    p_finish.add_argument("--penalty1", type=int)
    p_finish.add_argument("--penalty2", type=int)
    p_finish.add_argument("--rcg-file")
    p_finish.add_argument("--rcl-file")

    p_run = sub.add_parser("run", help="Run a tournament script")
    p_run.add_argument("--type", choices=["round_robin", "stepladder"], required=True)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return {
        "validate": cmd_validate,
        "begin": cmd_begin,
        "start-match": cmd_start_match,
        "event": cmd_record_event,
        "ingest-match": cmd_ingest_match,
        "analyze-match": cmd_analyze_match,
        "analyze-advanced": cmd_analyze_advanced,
        "simulate": cmd_simulate,
        "benchmark": cmd_benchmark,
        "seed": cmd_seed,
        "ratings": cmd_ratings,
        "export-match": cmd_export_match,
        "export-tournament": cmd_export_tournament,
        "notifications": cmd_notifications,
        "plugins": cmd_plugins,
        "web": cmd_web,
        "finish-tournament": cmd_finish_tournament,
        "finish-match-rcg": cmd_finish_match_rcg,
        "finish-match": cmd_finish,
        "run": cmd_run,
    }[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
