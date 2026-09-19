from __future__ import annotations
import argparse
from pathlib import Path
from graphics import generate_tournament_results


def analyze_and_plot(db_path: str | Path | None = None, tournament_id: str | None = None, output: str | Path | None = None):
    if not db_path or not tournament_id:
        raise ValueError('DB-backed mode requires --db and --tournament-id')
    return generate_tournament_results(Path(db_path), tournament_id, Path(output or 'Results_analysis/results_wdl.png'))


if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--db', required=True)
    p.add_argument('--tournament-id', required=True)
    p.add_argument('--output', default='Results_analysis/results_wdl.png')
    args=p.parse_args()
    print(analyze_and_plot(args.db, args.tournament_id, args.output))
