#!/bin/bash

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

cd Bins || { echo -e "${RED}Error: Bins directory not found${NC}" >&2; exit 1; }

for dir in */ ; do
    dir=${dir%/}
    errors=()
    
    if [ -f "$dir/start" ]; then
        start_file="$dir/start"
    elif [ -f "$dir/start.sh" ]; then
        start_file="$dir/start.sh"
    else
        printf "${RED}Error processing %s: %s${NC}\n" "$dir" "No start or start.sh file found [ERROR]" >&2
        continue
    fi

    teamname=$(grep '^teamname=' "$start_file" | cut -d'"' -f2)

    if [ -z "$teamname" ]; then
        printf "${RED}Error processing %s: %s${NC}\n" "$dir" "No teamname found in $start_file [ERROR]" >&2
        continue
    fi

    if [ "$dir" != "$teamname" ]; then
        mv "$dir" "$teamname" || {
            printf "${RED}Error processing %s: %s${NC}\n" "$dir" "Failed to rename directory [ERROR]" >&2
            continue
        }
        echo -e "Renamed ${YELLOW}$dir${NC} to ${GREEN}$teamname${NC} [${GREEN}OK${NC}]"
    else
        echo -e "${GREEN}$teamname${NC} [${GREEN}OK${NC}]"
    fi
done