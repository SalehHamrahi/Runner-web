from __future__ import annotations
import argparse
from pathlib import Path
from graphics import generate_tournament_network


def build_colored_match_graph(db_path: str | Path | None = None, tournament_id: str | None = None, output: str | Path | None = None):
    if not db_path or not tournament_id:
        raise ValueError('DB-backed mode requires --db and --tournament-id')
    return generate_tournament_network(Path(db_path), tournament_id, Path(output or 'Results_analysis/match_network_colored.png'))


if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--db', required=True)
    p.add_argument('--tournament-id', required=True)
    p.add_argument('--output', default='Results_analysis/match_network_colored.png')
    args=p.parse_args()
    print(build_colored_match_graph(args.db, args.tournament_id, args.output))
