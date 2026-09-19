#!/bin/bash
set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR" || exit 1

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

if [[ ! -f "config.conf" ]]; then
  echo -e "${RED}Error: config.conf not found. [ERROR]${NC}"
  exit 1
fi

TYPE=$(grep -E '^type=' config.conf | tail -n 1 | cut -d'=' -f2- | xargs)
if [[ -z "$TYPE" ]]; then
  echo -e "${RED}Error: 'type' is missing from config.conf. [ERROR]${NC}"
  exit 1
fi

if ! python3 runner.py validate; then
  echo -e "${RED}Team validation failed. Tournament will not start.${NC}"
  exit 1
fi

if [[ ! -s Games.txt ]] && [[ -f group_generator.py ]]; then
  echo -e "${CYAN}Games.txt is empty. Generating fixtures...${NC}"
  python3 group_generator.py || exit 1
fi

TOURNAMENT_ID=$(python3 runner.py begin)
if [[ -z "$TOURNAMENT_ID" ]]; then
  echo -e "${RED}Could not create Tournament ID. [ERROR]${NC}"
  exit 1
fi

export RUNNER_ROOT="$ROOT_DIR"
export RUNNER_TOURNAMENT_ID="$TOURNAMENT_ID"
export RUNNER_TOURNAMENT_DIR="$ROOT_DIR/tournaments/$TOURNAMENT_ID"
export RUNNER_DB="$ROOT_DIR/runner.db"
export RUNNER_LOG_DIR="$ROOT_DIR/tournaments/$TOURNAMENT_ID/logs"
export RUNNER_LOG_LEVEL="$(grep -E '^log_level=' config.conf | tail -n 1 | cut -d'=' -f2- | xargs)"
export RUNNER_LOG_LEVEL="${RUNNER_LOG_LEVEL:-INFO}"

LOG_LEVEL="${RUNNER_LOG_LEVEL:-INFO}"

echo -e "${YELLOW}Tournament${NC}: ${GREEN}${TOURNAMENT_ID}${NC}"
echo -e "${YELLOW}Type${NC}:      ${GREEN}${TYPE}${NC}"
echo -e "${YELLOW}Logs${NC}:      ${CYAN}${RUNNER_LOG_DIR}${NC}"

python3 runner.py event INFO "Tournament $TOURNAMENT_ID started" || true

case "$TYPE" in
  round_robin)
    exec "$ROOT_DIR/Group_tournament.sh"
    ;;
  stepladder)
    exec "$ROOT_DIR/Stepladder_tournament.sh"
    ;;
  *)
    echo -e "${RED}Unknown tournament type '$TYPE'. [ERROR]${NC}"
    exit 1
    ;;
esac
