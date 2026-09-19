#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

VERSION="$(tr -d '[:space:]' < VERSION)"
OUT_DIR="$ROOT_DIR/dist"
ARCHIVE="$OUT_DIR/Runner-$VERSION.zip"
RELEASE_DIR="$OUT_DIR/Runner-$VERSION"

rm -rf "$OUT_DIR"
mkdir -p "$RELEASE_DIR"

./scripts/quality_check.sh

python3 - "$ROOT_DIR" "$RELEASE_DIR" <<'PY'
from pathlib import Path
import shutil
import sys

src = Path(sys.argv[1])
dst = Path(sys.argv[2])
exclude_dirs = {'.git', '.venv', '__pycache__', 'tournaments', 'logs', 'reports', 'data', 'dist', 'Backup'}
exclude_dirs |= {'LogsJSON', 'Results_analysis'}
exclude_names = {'runner.db', 'Results.txt', 'Games.txt', 'Table.txt'}
for path in src.rglob('*'):
    rel = path.relative_to(src)
    if any(part in exclude_dirs for part in rel.parts):
        continue
    if path.name in exclude_names or path.suffix in {'.rcg', '.rcl', '.pyc', '.pyo'}:
        continue
    if path.is_dir():
        (dst / rel).mkdir(parents=True, exist_ok=True)
    elif path.is_file():
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
PY

# Release packages never contain live credentials.
sed -E 's#^discord_webhook_url=.*$#discord_webhook_url=#' \
  "$RELEASE_DIR/config.conf" > "$RELEASE_DIR/config.conf.tmp"
mv "$RELEASE_DIR/config.conf.tmp" "$RELEASE_DIR/config.conf"

printf '%s\n' "$VERSION" > "$RELEASE_DIR/VERSION"

(
  cd "$OUT_DIR"
  zip -qr "$ARCHIVE" "Runner-$VERSION"
)

python3 - "$ARCHIVE" <<'PY'
from pathlib import Path
import sys
import zipfile

archive = Path(sys.argv[1])
with zipfile.ZipFile(archive) as zf:
    bad = zf.testzip()
    if bad:
        raise SystemExit(f"ZIP integrity check failed at: {bad}")
print(f"Release ready: {archive}")
PY

printf '\033[1;32mRELEASE CREATED:\033[0m %s\n' "$ARCHIVE"
