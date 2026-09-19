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
get_config() { grep -E "^$1=" "$CONFIG_FILE" | tail -n 1 | cut -d'=' -f2- | xargs; }

FULLSTATE="$(get_config fullstate)"
SYNCH_MODE="$(get_config synch_mode)"
EXTRA_HALFS="$(get_config nr_extra_halfs)"
PENALTIES="$(get_config penalty_shoot_outs)"

[[ -n "$FULLSTATE" && -n "$SYNCH_MODE" ]] || { echo -e "${RED}Required configuration missing. [ERROR]${NC}"; exit 1; }
mkdir -p Logs

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

# The fixture generator writes --- as separators. They are not teams.
sed -i '/^\s*---\s*$/d' Games.txt

match_number=0
while true; do
    sed -i '/^\s*$/d' Games.txt
    line_count=$(grep -c . < Games.txt || true)
    if (( line_count < 2 )); then
        echo -e "${CYAN}Stepladder finished.${NC}"
        break
    fi

    team_one=$(sed -n '1p' Games.txt)
    team_two=$(sed -n '2p' Games.txt)
    sed -i '1,2d' Games.txt

    ((match_number+=1))
    echo -e "${CYAN}===============================================================${NC}"
    echo -e "${YELLOW}Match #${match_number}${NC}: ${GREEN}${team_one}${NC} vs ${GREEN}${team_two}${NC}"
    python3 runner.py event INFO "Starting Match #$match_number: $team_one vs $team_two" || true

    match_id="$(python3 runner.py start-match "$team_one" "$team_two" "$match_number")" || exit 1
    export RUNNER_MATCH_ID="$match_id"

    "$ROOT_DIR/rcssserver" \
        server::fullstate_l="$FULLSTATE" \
        server::fullstate_r="$FULLSTATE" \
        server::auto_mode=true \
        server::synch_mode="$SYNCH_MODE" \
        server::game_log_dir="$ROOT_DIR" \
        server::keepaway_log_dir="$ROOT_DIR" \
        server::text_log_dir="$ROOT_DIR" \
        server::nr_extra_halfs="$EXTRA_HALFS" \
        server::penalty_shoot_outs="$PENALTIES" \
        >"$RUNNER_TOURNAMENT_DIR/matches/match_${match_number}_server.log" 2>&1 &
    server_pid=$!

    sleep 2

    (
        cd "$ROOT_DIR/Bins/$team_one" || exit 1
        ./localStartAll
    ) >"$RUNNER_TOURNAMENT_DIR/matches/match_${match_number}_${team_one}.log" 2>&1 &

    sleep 2

    (
        cd "$ROOT_DIR/Bins/$team_two" || exit 1
        ./localStartAll
    ) >"$RUNNER_TOURNAMENT_DIR/matches/match_${match_number}_${team_two}.log" 2>&1 &

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

    # The winner advances. If the configured stepladder rule resolves a draw,
    # get_winner.py already returns team_two, so the same path handles both.
    if [[ -n "$winner" && "$winner" != "NONE" && "$winner" != "Draw (no penalties)" ]]; then
        printf '%s\n' "$winner" > tmpfile
        cat Games.txt >> tmpfile
        mv tmpfile Games.txt
    else
        # Defensive fallback. The rules engine should normally prevent this.
        printf '%s\n' "$team_two" > tmpfile
        cat Games.txt >> tmpfile
        mv tmpfile Games.txt
    fi

    rm -f "$ROOT_DIR"/*.rcg "$ROOT_DIR"/*.rcl
    sleep 1
done

python3 runner.py finish-tournament completed || true
