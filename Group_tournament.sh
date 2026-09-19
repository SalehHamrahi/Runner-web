#!/bin/bash
set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR" || exit 1

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

CONFIG_FILE="$ROOT_DIR/config.conf"
source_lines() { grep -E "^$1=" "$CONFIG_FILE" | tail -n 1 | cut -d'=' -f2- | xargs; }

if [[ ! -f "$CONFIG_FILE" ]]; then
    echo -e "${RED}Configuration file not found. [ERROR]${NC}"
    exit 1
fi

FULLSTATE="$(source_lines fullstate)"
SYNCH_MODE="$(source_lines synch_mode)"

[[ -n "$FULLSTATE" ]] || { echo -e "${RED}fullstate is missing. [ERROR]${NC}"; exit 1; }
[[ -n "$SYNCH_MODE" ]] || { echo -e "${RED}synch_mode is missing. [ERROR]${NC}"; exit 1; }

mkdir -p Logs

if [[ ! -x "$ROOT_DIR/rcssserver" ]]; then
    echo -e "${RED}rcssserver is missing or not executable. [ERROR]${NC}"
    exit 1
fi

if [[ -x "$ROOT_DIR/rcssmonitor" ]]; then
    "$ROOT_DIR/rcssmonitor" --auto-reconnect-mode on --auto-reconnect-wait 2 \
        >"$RUNNER_LOG_DIR/monitor.log" 2>&1 &
    monitor_pid=$!
else
    monitor_pid=""
fi

cleanup() {
    [[ -n "${server_pid:-}" ]] && kill "$server_pid" 2>/dev/null || true
    [[ -n "${monitor_pid:-}" ]] && kill "$monitor_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

mapfile -t schedule < <(grep -vE '^\s*(---)?\s*$' Games.txt)
if (( ${#schedule[@]} < 2 )); then
    echo -e "${RED}Games.txt does not contain enough teams. [ERROR]${NC}"
    exit 1
fi

match_number=0
for ((i=0; i+1<${#schedule[@]}; i+=2)); do
    TEAM="${schedule[i]}"
    TEAMT="${schedule[i+1]}"
    [[ -n "$TEAM" && -n "$TEAMT" ]] || continue

    ((match_number+=1))
    echo -e "${CYAN}===============================================================${NC}"
    echo -e "${YELLOW}Match #${match_number}${NC}: ${GREEN}${TEAM}${NC} vs ${GREEN}${TEAMT}${NC}"
    python3 runner.py event INFO "Starting Match #$match_number: $TEAM vs $TEAMT" || true

    match_id="$(python3 runner.py start-match "$TEAM" "$TEAMT" "$match_number")" || exit 1
    export RUNNER_MATCH_ID="$match_id"

    "$ROOT_DIR/rcssserver" \
        server::fullstate_l="$FULLSTATE" \
        server::fullstate_r="$FULLSTATE" \
        server::auto_mode=true \
        server::synch_mode="$SYNCH_MODE" \
        server::game_log_dir="$ROOT_DIR" \
        server::keepaway_log_dir="$ROOT_DIR" \
        server::text_log_dir="$ROOT_DIR" \
        server::nr_extra_halfs=0 \
        server::penalty_shoot_outs=false \
        >"$RUNNER_TOURNAMENT_DIR/matches/match_${match_number}_server.log" 2>&1 &
    server_pid=$!

    sleep 2

    (
        cd "$ROOT_DIR/Bins/$TEAM" || exit 1
        ./localStartAll
    ) >"$RUNNER_TOURNAMENT_DIR/matches/match_${match_number}_${TEAM}.log" 2>&1 &

    sleep 5

    (
        cd "$ROOT_DIR/Bins/$TEAMT" || exit 1
        ./localStartAll
    ) >"$RUNNER_TOURNAMENT_DIR/matches/match_${match_number}_${TEAMT}.log" 2>&1 &

    wait "$server_pid"
    server_exit=$?
    unset server_pid
    if (( server_exit != 0 )); then
        python3 runner.py event ERROR "RCSS server crashed during Match #$match_number (exit=$server_exit)" --match-id "$match_id" --notify-type server_crash || true
    fi
    sleep 1

    winner="$(python3 Analyzer/get_winner.py)"
    echo -e "${YELLOW}Winner${NC}: ${GREEN}${winner}${NC}"
    python3 runner.py event INFO "Match #$match_number finished: $winner" --match-id "$match_id" || true
    python3 runner.py finish-match-rcg "$match_id" || true

    "$ROOT_DIR/change_log_dir.sh" "$match_number" || true
    sleep 1
    rm -f "$ROOT_DIR"/*.rcg "$ROOT_DIR"/*.rcl

done

python3 table_generator.py
python3 runner.py finish-tournament completed || true
