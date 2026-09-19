#!/bin/bash

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

rm -rf Results_analysis LogsJSON/*.json

echo -e "${GREEN}Analyze...${NC}\n"
source ../.venv/bin/activate
python3 graph_bar_points.py
python3 match_graph_with_winners.py
./convert_logs.sh
./generate_reports.sh
python3 tactical_analysis.py