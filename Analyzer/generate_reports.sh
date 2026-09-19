#!/bin/bash

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

if ! command -v jq &>/dev/null; then
  echo -e "${RED}Error: jq is not installed. Please install it first.${NC}"
  echo -e "${YELLOW}sudo apt-get install jq${NC}"
  exit 1
fi

cd ./LogsJSON

for json_file in *.json; do
  left_team=$(jq -r '.leftTeam.leftTeam' "$json_file")
  right_team=$(jq -r '.rightTeam.rightTeam' "$json_file")
  left_goals=$(jq -r ".gameResult.\"$left_team\"" "$json_file")
  right_goals=$(jq -r ".gameResult.\"$right_team\"" "$json_file")

  output_file="${left_team}-${left_goals}-VS-${right_goals}-${right_team}.conf"

  l_pass=$(jq -r '.leftTeam.truePass' "$json_file")
  l_int=$(jq -r '.leftTeam.Intercept' "$json_file")
  l_shot_on=$(jq -r '.leftTeam.onTargetShoot' "$json_file")
  l_shot_off=$(jq -r '.leftTeam.offTarget' "$json_file")
  l_goals=$(jq -r '.leftTeam.goals' "$json_file")
  l_wpass=$(jq -r '.leftTeam.wrongPass' "$json_file")
  l_pacc=$(jq -r '.leftTeam.passAccuracy' "$json_file")
  l_sacc=$(jq -r '.leftTeam.shootAccuracy' "$json_file")
  l_pos=$(jq -r '.leftTeam.possession' "$json_file")
  l_dist=$(jq -r '.leftTeam.averageDistance10' "$json_file")
  l_stam=$(jq -r '.leftTeam.averageStamina10' "$json_file")
  l_crit=$(jq -r '[.leftTeam.stamina[] | select(.[0] < 20000) | "Player \(.[1]): \(.[0] | round)"] | join("، ")' "$json_file")

  r_pass=$(jq -r '.rightTeam.truePass' "$json_file")
  r_int=$(jq -r '.rightTeam.intercept' "$json_file")
  r_shot_on=$(jq -r '.rightTeam.onTargetShoot' "$json_file")
  r_shot_off=$(jq -r '.rightTeam.offTarget' "$json_file")
  r_goals=$(jq -r '.rightTeam.goals' "$json_file")
  r_wpass=$(jq -r '.rightTeam.wrongPass' "$json_file")
  r_pacc=$(jq -r '.rightTeam.passAccuracy' "$json_file")
  r_sacc=$(jq -r '.rightTeam.shootAccuracy' "$json_file")
  r_pos=$(jq -r '.rightTeam.possession' "$json_file")
  r_dist=$(jq -r '.rightTeam.averageDistance10' "$json_file")
  r_stam=$(jq -r '.rightTeam.averageStamina10' "$json_file")
  r_crit=$(jq -r '[.rightTeam.stamina[] | select(.[0] < 20000) | "Player \(.[1]): \(.[0] | round)"] | join("، ")' "$json_file")

  if ((left_goals > right_goals)); then
    winner="$left_team"
  elif ((right_goals > left_goals)); then
    winner="$right_team"
  else
    winner="Draw"
  fi

  report_content="========================================
Match Result: $left_team $left_goals - $right_goals $right_team
Winner: $winner
========================================
Key Statistics:
----------------------------------------
[$left_team]
    - Accurate Passes: $l_pass
    - Interceptions: $l_int
    - Shots on Target: $l_shot_on
    - Shots off Target: $l_shot_off
    - Goals: $l_goals
    - Inaccurate Passes: $l_wpass
    - Pass Accuracy: $l_pacc%
    - Shot Accuracy: $l_sacc%
    - Possession: $l_pos%
    - Avg. Movement: $l_dist
    - Avg. Stamina: $l_stam"

  if [ -n "$l_crit" ]; then
    report_content+="\n  - Low Stamina Players: $l_crit"
  fi

  report_content+="\n----------------------------------------
[$right_team]
    - Accurate Passes: $r_pass
    - Interceptions: $r_int
    - Shots on Target: $r_shot_on
    - Shots off Target: $r_shot_off
    - Goals: $r_goals
    - Inaccurate Passes: $r_wpass
    - Pass Accuracy: $r_pacc%
    - Shot Accuracy: $r_sacc%
    - Possession: $r_pos%
    - Avg. Movement: $r_dist
    - Avg. Stamina: $r_stam"

  if [ -n "$r_crit" ]; then
    report_content+="\n  - Low Stamina Players: $r_crit"
  fi

  report_content+="\n========================================"

  echo -e "$report_content" >"$output_file"
  echo -e "${YELLOW}Created report${NC}: ${GREEN}$output_file${NC}"
  mkdir -p ../Results_analysis/${json_file%.json}/
  mv "$output_file" ../Results_analysis/${json_file%.json}/
done

echo -e "${GREEN}All reports generated successfully!${NC}"
