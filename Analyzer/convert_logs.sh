#!/bin/bash

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_dir="./../Logs"
output_dir="./LogsJSON"

mkdir -p "$output_dir"

cd "$log_dir"

for file in *.rcg; do
    log_name="${file%.rcg}"

    if [[ -f "$log_name.rcl" ]]; then
        loganalyzer --path "$log_name"

        for f in *.json; do
            if [[ "$f" == "$log_name"*.json ]]; then
                mv "$f" "../Analyzer/$output_dir/${log_name}.json"
                echo -e "Convert ${YELLOW}${log_name}${NC} to ${GREEN}${log_name}.json${NC}"
            fi
        done
    fi
done
