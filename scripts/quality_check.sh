#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -z "${PYTHON_BIN:-}" ]]; then
  if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
    PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
  else
    PYTHON_BIN="python3"
  fi
else
  PYTHON_BIN="${PYTHON_BIN}"
fi

step() {
  printf '\n\033[1;36m==> %s\033[0m\n' "$1"
}

step "Dependency sanity"
"$PYTHON_BIN" - <<'PY_CHECK'
import sys
from importlib.metadata import version
from packaging.version import Version

required = {"matplotlib": Version("3.11.2")}
for name, minimum in required.items():
    installed = Version(version(name))
    if installed < minimum:
        raise SystemExit(f"{name}>={minimum} required, found {installed} under {sys.executable}. Run: {sys.executable} -m pip install -r requirements.txt")
print(f"Python: {sys.version.split()[0]} ({sys.executable})")
print(f"matplotlib: {version('matplotlib')}")
PY_CHECK

step "Python syntax"
"$PYTHON_BIN" -m compileall -q runner.py core web Analyzer group_generator.py table_generator.py

step "Unit/integration tests"
PYTHONWARNINGS="default::ResourceWarning" "$PYTHON_BIN" -m unittest discover -s tests -p "test_*.py" -v

step "Shell syntax"
while IFS= read -r -d '' script; do
  bash -n "$script"
done < <(find . -maxdepth 2 -type f -name '*.sh' -print0)

if command -v shellcheck >/dev/null 2>&1; then
  step "Shellcheck"
  shellcheck run.sh Group_tournament.sh Stepladder_tournament.sh \
    old_run.sh Backup.sh change_log_dir.sh log_compressor.sh log_extractor.sh rename.sh \
    Analyzer/*.sh 2>/dev/null || true
else
  printf '\033[1;33m[WARN]\033[0m shellcheck is not installed; skipping.\n'
fi

step "Required project files"
required=(
  runner.py config.conf requirements.txt run.sh
  Group_tournament.sh Stepladder_tournament.sh
  core/database.py core/notifications.py core/reports.py
  web/server.py tests/test_notifications.py tests/test_reports.py
)
for path in "${required[@]}"; do
  [[ -f "$path" ]] || { echo "Missing required file: $path" >&2; exit 1; }
done

step "CLI smoke test"
"$PYTHON_BIN" runner.py --version >/dev/null
"$PYTHON_BIN" runner.py --help >/dev/null
"$PYTHON_BIN" runner.py notifications --limit 1 >/dev/null

printf '\n\033[1;32mQUALITY CHECK PASSED\033[0m\n'
