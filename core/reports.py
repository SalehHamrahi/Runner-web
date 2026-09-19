from __future__ import annotations

import base64
import csv
import io
import json
import mimetypes
import shutil
import zipfile
from pathlib import Path
from typing import Any

from core.database import RunnerDB


def _json_load(value: str | None, default: Any):
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def _csv_bytes(rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> bytes:
    if fieldnames is None:
        keys: list[str] = []
        for row in rows:
            for key in row:
                if key not in keys:
                    keys.append(key)
        fieldnames = keys
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=fieldnames, extrasaction='ignore')
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return out.getvalue().encode('utf-8-sig')


def _data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode('ascii')


def _ensure_graphics(db_path: Path, match_id: int, out_dir: Path) -> dict[str, Path]:
    from Analyzer.graphics import generate_match_graphics
    files = generate_match_graphics(db_path, match_id, out_dir)
    return {name: Path(path) for name, path in files.items()}


def _ensure_tournament_graphics(db_path: Path, tournament_id: str, out_dir: Path) -> dict[str, Path]:
    from Analyzer.graphics import generate_tournament_graphics
    files = generate_tournament_graphics(db_path, tournament_id, out_dir)
    return {name: Path(path) for name, path in files.items()}


def build_match_report(db_path: Path, match_id: int, output_dir: Path) -> dict[str, Any]:
    db = RunnerDB(db_path)
    try:
        conn = db.conn
        match = conn.execute('SELECT * FROM matches WHERE id=?', (match_id,)).fetchone()
        if not match:
            raise ValueError(f'Match {match_id} not found')
        match = dict(match)
        team_stats = [dict(r) for r in conn.execute(
            'SELECT * FROM match_team_statistics WHERE match_id=? ORDER BY team', (match_id,)
        )]
        player_stats = [dict(r) for r in conn.execute(
            'SELECT * FROM match_player_statistics WHERE match_id=? ORDER BY team, unum', (match_id,)
        )]
        possession = [dict(r) for r in conn.execute(
            'SELECT team, start_cycle, end_cycle, cycles FROM match_possession_segments WHERE match_id=? ORDER BY start_cycle', (match_id,)
        )]
        events = [dict(r) for r in conn.execute(
            'SELECT cycle, event_type, team, unum, x, y, confidence, details_json FROM match_data_events WHERE match_id=? ORDER BY cycle, id', (match_id,)
        )]
        for row in events:
            row['details'] = _json_load(row.pop('details_json', None), {})
        actions = [dict(r) for r in conn.execute(
            'SELECT cycle, subcycle, team, unum, action_type, raw_action, args_json, attention_side, attention_unum, say_text FROM match_actions WHERE match_id=? ORDER BY cycle, subcycle, id', (match_id,)
        )]
        for row in actions:
            row['args'] = _json_load(row.pop('args_json', None), {})
        analytics = conn.execute('SELECT * FROM match_analytics_summary WHERE match_id=?', (match_id,)).fetchone()
        advanced = conn.execute('SELECT * FROM match_advanced_analytics WHERE match_id=?', (match_id,)).fetchone()
        simulation = conn.execute('SELECT * FROM simulation_runs WHERE tournament_id=? ORDER BY id DESC LIMIT 1', (match['tournament_id'],)).fetchone()
    finally:
        db.close()

    output_dir.mkdir(parents=True, exist_ok=True)
    graphics_dir = output_dir / 'graphics'
    graphics_warning = None
    try:
        graphics = _ensure_graphics(db_path, match_id, graphics_dir)
    except Exception as exc:
        graphics = {}
        graphics_warning = f"Graphics generation skipped: {type(exc).__name__}: {exc}"
    report = {
        'report_type': 'match',
        'report_version': 1,
        'match': match,
        'team_statistics': team_stats,
        'player_statistics': player_stats,
        'possession_segments': possession,
        'events': events,
        'actions': actions,
        'analytics': _json_load(analytics['summary_json'] if analytics else None, None),
        'advanced_analytics': _json_load(advanced['data_json'] if advanced else None, None),
        'latest_simulation': _json_load(simulation['result_json'] if simulation else None, None),
        'graphics': {k: str(v) for k, v in graphics.items()},
        'warnings': [graphics_warning] if graphics_warning else [],
    }
    (output_dir / 'match_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


def build_tournament_report(db_path: Path, tournament_id: str, output_dir: Path) -> dict[str, Any]:
    db = RunnerDB(db_path)
    try:
        conn = db.conn
        tournament = conn.execute('SELECT * FROM tournaments WHERE id=?', (tournament_id,)).fetchone()
        if not tournament:
            raise ValueError(f'Tournament {tournament_id} not found')
        tournament = dict(tournament)
        matches = [dict(r) for r in conn.execute(
            'SELECT * FROM matches WHERE tournament_id=? ORDER BY COALESCE(match_number,id)', (tournament_id,)
        )]
        teams = [dict(r) for r in conn.execute(
            'SELECT name, valid, validation_message FROM teams WHERE tournament_id=? ORDER BY name', (tournament_id,)
        )]
        simulations = [dict(r) for r in conn.execute(
            'SELECT id, simulation_type, runs, seed, parameters_json, result_json, created_at FROM simulation_runs WHERE tournament_id=? ORDER BY id DESC', (tournament_id,)
        )]
        benchmarks = [dict(r) for r in conn.execute(
            'SELECT id, team1, team2, runs, seed, result_json, created_at FROM benchmark_runs WHERE tournament_id=? ORDER BY id DESC', (tournament_id,)
        )]
    finally:
        db.close()

    output_dir.mkdir(parents=True, exist_ok=True)
    graphics_dir = output_dir / 'graphics'
    graphics_warning = None
    try:
        graphics = _ensure_tournament_graphics(db_path, tournament_id, graphics_dir)
    except Exception as exc:
        graphics = {}
        graphics_warning = f"Graphics generation skipped: {type(exc).__name__}: {exc}"

    standings = _simple_standings(matches, [t['name'] for t in teams])
    report = {
        'report_type': 'tournament',
        'report_version': 1,
        'tournament': tournament,
        'teams': teams,
        'matches': matches,
        'standings': standings,
        'simulations': [{**r, 'parameters': _json_load(r.pop('parameters_json', None), {}), 'result': _json_load(r.pop('result_json', None), {})} for r in simulations],
        'benchmarks': [{**r, 'result': _json_load(r.pop('result_json', None), {})} for r in benchmarks],
        'graphics': {k: str(v) for k, v in graphics.items()},
        'warnings': [graphics_warning] if graphics_warning else [],
    }
    (output_dir / 'tournament_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


def _simple_standings(matches: list[dict[str, Any]], teams: list[str]) -> list[dict[str, Any]]:
    table = {t: {'team': t, 'played': 0, 'wins': 0, 'draws': 0, 'losses': 0, 'gf': 0, 'ga': 0, 'gd': 0, 'points': 0} for t in teams}
    for m in matches:
        if m.get('status') != 'completed' or m.get('score1') is None or m.get('score2') is None:
            continue
        a, b = m['team1'], m['team2']
        sa, sb = int(m['score1']), int(m['score2'])
        for t, gf, ga in ((a, sa, sb), (b, sb, sa)):
            table.setdefault(t, {'team': t, 'played': 0, 'wins': 0, 'draws': 0, 'losses': 0, 'gf': 0, 'ga': 0, 'gd': 0, 'points': 0})
            table[t]['played'] += 1
            table[t]['gf'] += gf
            table[t]['ga'] += ga
        winner = m.get('winner')
        if winner == a or (not winner and sa > sb):
            table[a]['wins'] += 1
            table[a]['points'] += 3
            table[b]['losses'] += 1
        elif winner == b or (not winner and sb > sa):
            table[b]['wins'] += 1
            table[b]['points'] += 3
            table[a]['losses'] += 1
        else:
            table[a]['draws'] += 1
            table[b]['draws'] += 1
            table[a]['points'] += 1
            table[b]['points'] += 1
    for r in table.values():
        r['gd'] = r['gf'] - r['ga']
    return sorted(table.values(), key=lambda x: (-x['points'], -x['gd'], -x['gf'], x['team']))

def _base_css() -> str:
    return '''<style>
body{font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif;background:#0a0f1d;color:#e5e7eb;margin:0;padding:32px} .wrap{max-width:1200px;margin:auto}.header{margin-bottom:28px}.eyebrow{color:#22d3ee;font-size:12px;letter-spacing:.15em;font-weight:700}.h1{font-size:32px;font-weight:800}.muted{color:#94a3b8}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}.card{background:#111827;border:1px solid #243047;border-radius:16px;padding:18px}.value{font-size:26px;font-weight:800}.section{margin-top:22px}.section h2{font-size:18px}.table{width:100%;border-collapse:collapse}.table th,.table td{padding:10px 12px;border-bottom:1px solid #243047;text-align:left}.img{max-width:100%;border-radius:14px;border:1px solid #243047;margin-top:10px}.row{display:flex;gap:18px;align-items:flex-start;flex-wrap:wrap}.col{flex:1;min-width:320px}</style>'''


def match_html(report: dict[str, Any]) -> str:
    m = report['match']; stats = report['team_statistics']; players = report['player_statistics']
    cards = ''
    for s in stats:
        cards += f"<div class='card'><div class='muted'>{s['team']}</div><div class='value'>{float(s.get('possession_pct') or 0):.1f}%</div><div class='muted'>possession</div></div>"
    team_rows = ''.join(f"<tr><td>{s['team']}</td><td>{s['passes_completed']}</td><td>{s['pass_accuracy_pct'] if s['pass_accuracy_pct'] is not None else '—'}</td><td>{s['shots']}</td><td>{s['goals']}</td><td>{float(s['avg_territory'])*100:.1f}%</td><td>{float(s['avg_space_control'])*100:.1f}%</td></tr>" for s in stats)
    graphics = ''.join(f"<div class='col'><h3>{name.title()}</h3><img class='img' src='{_data_uri(Path(path))}'></div>" for name, path in report['graphics'].items() if Path(path).exists())
    warning_html = ''.join(f"<div class='card'><div class='muted'>Warning</div><div>{w}</div></div>" for w in report.get('warnings', []))
    return f"<!doctype html><html><head><meta charset='utf-8'><title>Match {m['id']} Report</title>{_base_css()}</head><body><div class='wrap'><div class='header'><div class='eyebrow'>RUNNER MATCH REPORT</div><div class='h1'>{m['team1']} {m.get('score1','—')} — {m.get('score2','—')} {m['team2']}</div><div class='muted'>Match #{m.get('match_number','—')} · Winner: {m.get('winner') or 'Draw'}</div></div><div class='grid'>{cards}{warning_html}</div><div class='section'><h2>Team Statistics</h2><table class='table'><tr><th>Team</th><th>Passes</th><th>Accuracy</th><th>Shots</th><th>Goals</th><th>Territory</th><th>Space</th></tr>{team_rows}</table></div><div class='section row'>{graphics}</div><div class='section'><h2>Events</h2><div class='muted'>{len(report['events'])} events recorded · {len(report['actions'])} agent actions</div></div></div></body></html>"


def tournament_html(report: dict[str, Any]) -> str:
    t = report['tournament']; standings = report['standings']
    rows = ''.join(f"<tr><td>{i+1}</td><td>{r['team']}</td><td>{r['played']}</td><td>{r['wins']}</td><td>{r['draws']}</td><td>{r['losses']}</td><td>{r['gf']}</td><td>{r['ga']}</td><td>{r['gd']}</td><td>{r['points']}</td></tr>" for i,r in enumerate(standings))
    graphics = ''.join(f"<div class='col'><h3>{name.title()}</h3><img class='img' src='{_data_uri(Path(path))}'></div>" for name,path in report['graphics'].items() if Path(path).exists())
    warning_html = ''.join(f"<div class='card'><div class='muted'>Warning</div><div>{w}</div></div>" for w in report.get('warnings', []))
    return f"<!doctype html><html><head><meta charset='utf-8'><title>{t['id']} Report</title>{_base_css()}</head><body><div class='wrap'><div class='header'><div class='eyebrow'>RUNNER TOURNAMENT REPORT</div><div class='h1'>{t['id']}</div><div class='muted'>{t['type']} · {t['status']}</div></div><div class='section'><div class='grid'>{warning_html}</div></div><div class='section'><h2>Standings</h2><table class='table'><tr><th>#</th><th>Team</th><th>MP</th><th>W</th><th>D</th><th>L</th><th>GF</th><th>GA</th><th>GD</th><th>Pts</th></tr>{rows}</table></div><div class='section row'>{graphics}</div><div class='section'><h2>Match Archive</h2><div class='muted'>{len(report['matches'])} matches · {len(report['teams'])} teams</div></div></div></body></html>"


def export_match(db_path: Path, match_id: int, fmt: str, output_root: Path) -> Path:
    report_dir = output_root / 'match' / str(match_id)
    report = build_match_report(db_path, match_id, report_dir)
    if fmt == 'json': return report_dir / 'match_report.json'
    if fmt == 'html':
        path = report_dir / 'match_report.html'; path.write_text(match_html(report), encoding='utf-8'); return path
    if fmt == 'csv':
        bundle = report_dir / 'match_report_csv'
        bundle.mkdir(exist_ok=True)
        (bundle/'team_statistics.csv').write_bytes(_csv_bytes(report['team_statistics']))
        (bundle/'player_statistics.csv').write_bytes(_csv_bytes(report['player_statistics']))
        (bundle/'events.csv').write_bytes(_csv_bytes([{k: v for k,v in e.items() if k!='details'} for e in report['events']]))
        (bundle/'actions.csv').write_bytes(_csv_bytes([{k: v for k,v in a.items() if k!='args'} for a in report['actions']]))
        zip_path=report_dir/'match_report_csv.zip'
        with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED) as z:
            for p in bundle.iterdir(): z.write(p,p.name)
        return zip_path
    if fmt == 'pdf': return _pdf_from_html_data(report, report_dir/'match_report.pdf', title=f"{report['match']['team1']} {report['match'].get('score1','—')} - {report['match'].get('score2','—')} {report['match']['team2']}")
    if fmt == 'graphics':
        graphics_paths = [Path(p) for p in report.get('graphics', {}).values()]
        graphics_paths = [p for p in graphics_paths if p.exists() and p.is_file()]
        if not graphics_paths:
            warning = report.get('warnings') or ['No graphics are available for this match']
            raise RuntimeError(warning[0])
        zip_path=report_dir/'match_graphics.zip'
        with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED) as z:
            for p in graphics_paths: z.write(p, p.name)
        return zip_path
    raise ValueError(f'Unsupported match export format: {fmt}')


def export_tournament(db_path: Path, tournament_id: str, fmt: str, output_root: Path) -> Path:
    report_dir = output_root / 'tournament' / tournament_id
    report = build_tournament_report(db_path, tournament_id, report_dir)
    if fmt == 'json': return report_dir/'tournament_report.json'
    if fmt == 'html':
        path=report_dir/'tournament_report.html'; path.write_text(tournament_html(report),encoding='utf-8'); return path
    if fmt == 'csv':
        bundle=report_dir/'tournament_report_csv'; bundle.mkdir(exist_ok=True)
        (bundle/'standings.csv').write_bytes(_csv_bytes(report['standings']))
        (bundle/'matches.csv').write_bytes(_csv_bytes(report['matches']))
        (bundle/'teams.csv').write_bytes(_csv_bytes(report['teams']))
        zip_path=report_dir/'tournament_report_csv.zip'
        with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED) as z:
            for p in bundle.iterdir(): z.write(p,p.name)
        return zip_path
    if fmt == 'pdf': return _pdf_from_html_data(report, report_dir/'tournament_report.pdf', title=f"Tournament {tournament_id}")
    if fmt == 'graphics':
        graphics_paths = [Path(p) for p in report.get('graphics', {}).values()]
        graphics_paths = [p for p in graphics_paths if p.exists() and p.is_file()]
        if not graphics_paths:
            warning = report.get('warnings') or ['No graphics are available for this tournament']
            raise RuntimeError(warning[0])
        zip_path=report_dir/'tournament_graphics.zip'
        with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED) as z:
            for p in graphics_paths: z.write(p, p.name)
        return zip_path
    raise ValueError(f'Unsupported tournament export format: {fmt}')


def _pdf_from_html_data(report: dict[str, Any], path: Path, title: str) -> Path:
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from matplotlib.backends.backend_pdf import PdfPages
    except Exception as exc:
        raise RuntimeError('PDF export requires matplotlib in the project virtual environment') from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    with PdfPages(path) as pdf:
        fig = plt.figure(figsize=(11.69, 8.27), facecolor='#0a0f1d')
        ax = fig.add_axes([0, 0, 1, 1])
        ax.axis('off')
        ax.set_facecolor('#0a0f1d')
        ax.text(.06, .90, title, color='#e5e7eb', fontsize=24, fontweight='bold')
        ax.text(.06, .84, f"Generated by Runner Reports & Export · report v{report['report_version']}", color='#94a3b8', fontsize=10)
        if report['report_type'] == 'match':
            m = report['match']
            lines = [
                f"Score: {m.get('score1', '—')} - {m.get('score2', '—')}",
                f"Winner: {m.get('winner') or 'Draw'}",
                f"Events: {len(report['events'])}",
                f"Agent actions: {len(report['actions'])}",
            ]
        else:
            lines = [
                f"Status: {report['tournament'].get('status')}",
                f"Matches: {len(report['matches'])}",
                f"Teams: {len(report['teams'])}",
            ]
        y = .76
        for line in lines:
            ax.text(.08, y, line, color='#e5e7eb', fontsize=14)
            y -= .06
        pdf.savefig(fig, facecolor=fig.get_facecolor())
        plt.close(fig)
        for _, img in report.get('graphics', {}).items():
            p = Path(img)
            if not p.exists():
                continue
            fig = plt.figure(figsize=(11.69, 8.27), facecolor='#0a0f1d')
            ax = fig.add_axes([.03, .03, .94, .94])
            ax.axis('off')
            ax.imshow(plt.imread(p))
            pdf.savefig(fig, facecolor=fig.get_facecolor())
            plt.close(fig)
    return path
