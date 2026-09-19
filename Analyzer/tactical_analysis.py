from __future__ import annotations
import argparse
from pathlib import Path
from graphics import generate_match_graphics


def process_match(db_path: str | Path, match_id: int, output_dir: str | Path):
    return generate_match_graphics(Path(db_path), match_id, Path(output_dir))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description='Tactical analysis: analytics DB-backed graphics')
    parser.add_argument('--db', required=True)
    parser.add_argument('--match-id', type=int, required=True)
    parser.add_argument('--output', default='Results_analysis')
    args=parser.parse_args()
    print(process_match(args.db, args.match_id, args.output))
