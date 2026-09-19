from __future__ import annotations

import math
import random
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .database import RunnerDB

SIMULATION_VERSION = 1
DEFAULT_ELO = 1500.0
DEFAULT_K = 32.0


def _completed_matches(db: RunnerDB, tournament_id: str | None = None) -> list[dict[str, Any]]:
    with db.conn as conn:
        sql = "SELECT id, tournament_id, team1, team2, score1, score2, winner, status FROM matches WHERE status='completed' AND score1 IS NOT NULL AND score2 IS NOT NULL"
        params: tuple[Any, ...] = ()
        if tournament_id is not None:
            sql += " AND tournament_id=?"
            params = (tournament_id,)
        sql += " ORDER BY finished_at, id"
        return [dict(r) for r in conn.execute(sql, params)]


def elo_ratings(db: RunnerDB, tournament_id: str | None = None, k: float = DEFAULT_K) -> dict[str, float]:
    matches = _completed_matches(db, tournament_id)
    teams: set[str] = set()
    for m in matches:
        teams.update((m['team1'], m['team2']))
    ratings = {team: DEFAULT_ELO for team in sorted(teams)}
    for m in matches:
        a, b = m['team1'], m['team2']
        sa, sb = int(m['score1']), int(m['score2'])
        actual_a = 1.0 if sa > sb else 0.0 if sb > sa else 0.5
        expected_a = 1.0 / (1.0 + 10 ** ((ratings[b] - ratings[a]) / 400.0))
        ratings[a] += k * (actual_a - expected_a)
        ratings[b] += k * ((1.0 - actual_a) - (1.0 - expected_a))
    return ratings


def team_goal_rates(db: RunnerDB, tournament_id: str | None = None) -> dict[str, dict[str, float]]:
    matches = _completed_matches(db, tournament_id)
    gf = defaultdict(int)
    ga = defaultdict(int)
    gp = defaultdict(int)
    for m in matches:
        a, b = m['team1'], m['team2']
        sa, sb = int(m['score1']), int(m['score2'])
        gf[a] += sa; ga[a] += sb; gp[a] += 1
        gf[b] += sb; ga[b] += sa; gp[b] += 1
    total_goals = sum(gf.values())
    total_games = sum(gp.values()) / 2.0
    league_avg = max(0.2, total_goals / max(1.0, total_games * 2.0))
    out: dict[str, dict[str, float]] = {}
    for team in gp:
        games = gp[team]
        attack = (gf[team] / games) if games else league_avg
        concede = (ga[team] / games) if games else league_avg
        out[team] = {
            'attack': 0.65 * attack + 0.35 * league_avg,
            'concede': 0.65 * concede + 0.35 * league_avg,
        }
    return out


def _poisson(rng: random.Random, lam: float) -> int:
    lam = max(1e-9, min(12.0, float(lam)))
    limit = math.exp(-lam)
    k = 0
    p = 1.0
    while p > limit:
        k += 1
        p *= rng.random()
    return k - 1


def expected_goals(team_a: str, team_b: str, ratings: dict[str, float], rates: dict[str, dict[str, float]]) -> tuple[float, float]:
    ra, rb = ratings.get(team_a, DEFAULT_ELO), ratings.get(team_b, DEFAULT_ELO)
    elo_a = 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))
    elo_delta = elo_a - 0.5
    league = statistics.fmean([v['attack'] for v in rates.values()]) if rates else 1.2
    a_rate = rates.get(team_a, {'attack': league, 'concede': league})
    b_rate = rates.get(team_b, {'attack': league, 'concede': league})
    base_a = 0.55 * a_rate['attack'] + 0.45 * b_rate['concede']
    base_b = 0.55 * b_rate['attack'] + 0.45 * a_rate['concede']
    return (max(0.15, base_a * (1.0 + 0.40 * elo_delta)), max(0.15, base_b * (1.0 - 0.40 * elo_delta)))


def simulate_match(team_a: str, team_b: str, ratings: dict[str, float], rates: dict[str, dict[str, float]], runs: int, seed: int | None = None) -> dict[str, Any]:
    if runs <= 0:
        raise ValueError('runs must be > 0')
    rng = random.Random(seed)
    gx, gy = expected_goals(team_a, team_b, ratings, rates)
    wins_a = wins_b = draws = 0
    goals_a = goals_b = 0
    margins: list[int] = []
    for _ in range(runs):
        sa = _poisson(rng, gx); sb = _poisson(rng, gy)
        goals_a += sa; goals_b += sb; margins.append(sa - sb)
        if sa > sb: wins_a += 1
        elif sb > sa: wins_b += 1
        else: draws += 1
    return {
        'team1': team_a, 'team2': team_b, 'runs': runs, 'seed': seed,
        'expected_goals': {team_a: round(gx, 3), team_b: round(gy, 3)},
        'win_probability': {team_a: round(wins_a / runs * 100, 2), 'draw': round(draws / runs * 100, 2), team_b: round(wins_b / runs * 100, 2)},
        'average_score': {team_a: round(goals_a / runs, 3), team_b: round(goals_b / runs, 3)},
        'average_goal_difference': round(statistics.fmean(margins), 3),
        'rating': {team_a: round(ratings.get(team_a, DEFAULT_ELO), 1), team_b: round(ratings.get(team_b, DEFAULT_ELO), 1)},
        'simulation_version': SIMULATION_VERSION,
    }


def auto_seed(db: RunnerDB, tournament_id: str) -> list[dict[str, Any]]:
    ratings = elo_ratings(db, tournament_id)
    rates = team_goal_rates(db, tournament_id)
    teams = sorted(set(ratings) | set(rates))
    return [
        {'seed': i + 1, 'team': team, 'elo': round(ratings.get(team, DEFAULT_ELO), 1), 'attack': round(rates.get(team, {}).get('attack', 0.0), 3), 'concede': round(rates.get(team, {}).get('concede', 0.0), 3)}
        for i, team in enumerate(sorted(teams, key=lambda t: (-ratings.get(t, DEFAULT_ELO), t)))
    ]


def simulate_round_robin(db: RunnerDB, tournament_id: str, runs: int = 10000, seed: int | None = 42) -> dict[str, Any]:
    if runs <= 0:
        raise ValueError('runs must be > 0')
    with db.conn as conn:
        tournament = conn.execute('SELECT * FROM tournaments WHERE id=?', (tournament_id,)).fetchone()
        if not tournament:
            raise ValueError(f'Tournament {tournament_id} not found')
        team_rows = conn.execute('SELECT DISTINCT name FROM teams WHERE tournament_id=?', (tournament_id,)).fetchall()
    teams = [r[0] for r in team_rows]
    if len(teams) < 2:
        raise ValueError('Tournament needs at least two teams')
    ratings = elo_ratings(db, tournament_id)
    rates = team_goal_rates(db, tournament_id)
    rng = random.Random(seed)
    champion = Counter = defaultdict(int)
    top3 = defaultdict(int)
    points_sum = defaultdict(float)
    rank_sum = defaultdict(float)
    pairings = [(a, b) for i, a in enumerate(teams) for b in teams[i + 1:]]
    for _ in range(runs):
        pts = {t: 0 for t in teams}
        gf = {t: 0 for t in teams}
        ga = {t: 0 for t in teams}
        gd = {t: 0 for t in teams}
        for a, b in pairings:
            gx, gy = expected_goals(a, b, ratings, rates)
            sa = _poisson(rng, gx); sb = _poisson(rng, gy)
            gf[a] += sa; ga[a] += sb; gf[b] += sb; ga[b] += sa
            gd[a] += sa - sb; gd[b] += sb - sa
            if sa > sb: pts[a] += 3
            elif sb > sa: pts[b] += 3
            else: pts[a] += 1; pts[b] += 1
        ranking = sorted(teams, key=lambda t: (-pts[t], -gd[t], -gf[t], -ratings.get(t, DEFAULT_ELO), t))
        for idx, team in enumerate(ranking, start=1):
            rank_sum[team] += idx
            points_sum[team] += pts[team]
            if idx == 1: champion[team] += 1
            if idx <= 3: top3[team] += 1
    ranking = []
    for team in sorted(teams, key=lambda t: (-champion[t], -top3[t], rank_sum[t], t)):
        ranking.append({
            'team': team,
            'champion_probability': round(champion[team] / runs * 100.0, 2),
            'top3_probability': round(top3[team] / runs * 100.0, 2),
            'expected_points': round(points_sum[team] / runs, 2),
            'expected_rank': round(rank_sum[team] / runs, 2),
            'elo': round(ratings.get(team, DEFAULT_ELO), 1),
        })
    return {
        'tournament_id': tournament_id,
        'runs': runs,
        'seed': seed,
        'format': 'round_robin',
        'ranking': ranking,
        'seeds': auto_seed(db, tournament_id),
        'simulation_version': SIMULATION_VERSION,
        'generated_at': datetime.now(timezone.utc).isoformat(),
    }


def benchmark(db: RunnerDB, team_a: str, team_b: str, tournament_id: str | None = None, runs: int = 10000, seed: int | None = 42) -> dict[str, Any]:
    ratings = elo_ratings(db, tournament_id)
    rates = team_goal_rates(db, tournament_id)
    result = simulate_match(team_a, team_b, ratings, rates, runs, seed)
    with db.conn as conn:
        rows = conn.execute(
            "SELECT team1,team2,score1,score2,winner FROM matches WHERE status='completed' AND ((team1=? AND team2=?) OR (team1=? AND team2=?))",
            (team_a, team_b, team_b, team_a),
        ).fetchall()
    historical = {'matches': len(rows), 'wins': {team_a: 0, team_b: 0}, 'draws': 0}
    for r in rows:
        if r['winner'] == team_a: historical['wins'][team_a] += 1
        elif r['winner'] == team_b: historical['wins'][team_b] += 1
        else: historical['draws'] += 1
    result['historical_head_to_head'] = historical
    result['mode'] = 'statistical_monte_carlo'
    return result
