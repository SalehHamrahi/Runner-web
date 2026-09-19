def create_clean_team_table():
    try:
        with open('teams.txt', 'r') as file:
            teams = [line.strip() for line in file if line.strip()]
        
        if not teams:
            with open('Table.txt', 'w') as f:
                f.write("No teams found in teams.txt\n")
            return

        matches = []
        try:
            with open('Results.txt', 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split()
                    if len(parts) < 7 or parts[2] != '-':
                        continue
                    teamA = parts[0]
                    teamB = parts[4]
                    scoreA = parts[1]
                    scoreB = parts[3]
                    matches.append((teamA, teamB, scoreA, scoreB))
        except FileNotFoundError:
            pass

        match_dict = {}
        points = {team: 0 for team in teams}
        goals_for = {team: 0 for team in teams}
        goals_against = {team: 0 for team in teams}

        for (teamA, teamB, scoreA, scoreB) in matches:
            if teamA in teams and teamB in teams:
                match_dict[(teamA, teamB)] = (scoreA, scoreB)
                match_dict[(teamB, teamA)] = (scoreB, scoreA)
                
                sa, sb = int(scoreA), int(scoreB)
                goals_for[teamA] += sa
                goals_against[teamA] += sb
                goals_for[teamB] += sb
                goals_against[teamB] += sa
                
                if sa > sb:
                    points[teamA] += 3
                elif sa < sb:
                    points[teamB] += 3
                else:
                    points[teamA] += 1
                    points[teamB] += 1

        tgd = {team: goals_for[team] - goals_against[team] for team in teams}
        sorted_teams = sorted(teams, key=lambda x: (-points[x], -tgd[x]))
        
        groups = []
        if sorted_teams:
            current_group = [sorted_teams[0]]
            prev_key = (points[sorted_teams[0]], tgd[sorted_teams[0]])
            for team in sorted_teams[1:]:
                key = (points[team], tgd[team])
                if key == prev_key:
                    current_group.append(team)
                else:
                    groups.append(current_group)
                    current_group = [team]
                    prev_key = key
            groups.append(current_group)
        
        rank_dict = {}
        current_rank = 1
        for group in groups:
            for team in group:
                rank_dict[team] = current_rank
            current_rank += len(group)

        max_len = max(len(team) for team in teams)
        col_width = max(max_len, 7)

        with open('Table.txt', 'w') as outfile:
            top_border = "+" + "-"*(col_width+2) + "+" + ("-"*(col_width+2) + "+")*len(teams) + "------+--------+-----+"
            outfile.write(top_border + '\n')
            
            header = "|" + " "*(col_width+2) + "|"
            for team in teams:
                header += f" {team[:col_width]:^{col_width}} |"
            header += " Rank | Points | TGD |"
            outfile.write(header + '\n')
            
            separator = top_border.replace("+", "|").replace("-", "=")
            outfile.write(separator + '\n')
            
            row_separator = "+" + "-"*(col_width+2) + "+" + ("-"*(col_width+2) + "+")*len(teams) + "------+--------+-----+"
            for row_team in teams:
                row = f"| {row_team[:col_width]:<{col_width}} |"
                for col_team in teams:
                    if row_team == col_team:
                        cell = '#'
                    else:
                        result = match_dict.get((row_team, col_team))
                        cell = f"{result[0]}-{result[1]}" if result else ' '
                    row += f" {cell:^{col_width}} |"
                
                rank_str = str(rank_dict.get(row_team, ''))
                points_str = str(points.get(row_team, ''))
                tgd_str = str(tgd.get(row_team, ''))
                rank_display = rank_str.center(6)
                points_display = points_str.center(8)
                tgd_display = tgd_str.center(5)
                row += f"{rank_display}|{points_display}|{tgd_display}|"
                
                outfile.write(row + '\n')
                outfile.write(row_separator + '\n')
    
    except FileNotFoundError:
        with open('Table.txt', 'w') as f:
            f.write("teams.txt not found\n")

create_clean_team_table()