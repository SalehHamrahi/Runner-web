import os
import json
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle, Patch
import numpy as np

MAIN_OUTPUT_DIR = 'Results_analysis'
os.makedirs(MAIN_OUTPUT_DIR, exist_ok=True)

def draw_field(ax):
    ax.set_xlim(0, 120)
    ax.set_ylim(0, 80)
    ax.set_facecolor('#2e8b57')
    ax.set_aspect('equal')
    ax.axis('off')

    ax.plot([0, 0, 120, 120, 0], [0, 80, 80, 0, 0], color='white', linewidth=2)
    ax.plot([60, 60], [0, 80], color='white', linewidth=2)
    
    ax.plot([0, 18, 18, 0], [30, 30, 50, 50], color='white')
    ax.plot([102, 120, 120, 102], [30, 30, 50, 50], color='white')
    ax.plot([102, 102], [30, 50], color='white')
    
    center_circle = Circle((60, 40), 10, color='white', fill=False, linewidth=2)
    ax.add_patch(center_circle)
    
    regions = {
        'A': (15, 65), 'B': (15, 40), 'C': (15, 15),
        'D': (60, 65), 'E': (60, 40), 'F': (60, 15),
        'G': (105, 65), 'H': (105, 40), 'I': (105, 15)
    }
    
    for region, pos in regions.items():
        ax.text(
            pos[0], pos[1], region, color='white', 
            fontsize=12, ha='center', va='center', weight='bold',
            bbox=dict(facecolor='black', alpha=0.5, boxstyle='round')
        )

def draw_heatmap_on_field(ax, left_team_name, right_team_name, left_region_data, right_region_data):
    all_values = list(left_region_data.values()) + list(right_region_data.values())
    max_value = max(all_values) if all_values else 1
    if max_value == 0:
        max_value = 1
    norm = plt.Normalize(0, max_value)
    
    cmap_left = plt.cm.Blues
    cmap_right = plt.cm.Reds
    
    region_width = 30
    region_height = 80 / 3.25
    
    regions = {
        'A': (15, 65), 'B': (15, 40), 'C': (15, 15),
        'D': (60, 65), 'E': (60, 40), 'F': (60, 15),
        'G': (105, 65), 'H': (105, 40), 'I': (105, 15)
    }
    
    for region_letter, center in regions.items():
        x_center, y_center = center
        x0 = x_center - region_width / 2
        y0 = y_center - region_height / 2
        
        left_value = left_region_data.get(region_letter, 0)
        left_color = cmap_left(norm(left_value))
        rect_left = Rectangle(
            (x0, y0), 
            width=region_width/2, 
            height=region_height, 
            color=left_color, 
            alpha=0.7,
            zorder=1
        )
        ax.add_patch(rect_left)
        
        right_value = right_region_data.get(region_letter, 0)
        right_color = cmap_right(norm(right_value))
        rect_right = Rectangle(
            (x0 + region_width/2, y0), 
            width=region_width/2, 
            height=region_height, 
            color=right_color, 
            alpha=0.7,
            zorder=1
        )
        ax.add_patch(rect_right)
        
        ax.text(
            x0 + region_width/4, y0 + region_height/2,
            f'{left_value}', 
            ha='center', va='center', 
            color='black',
            fontsize=8,
            zorder=10
        )
        ax.text(
            x0 + 3*region_width/4, y0 + region_height/2,
            f'{right_value}', 
            ha='center', va='center', 
            color='black',
            fontsize=8,
            zorder=10
        )
    
    legend_elements = [
        Patch(facecolor=cmap_left(0.7), label=f'{left_team_name}'),
        Patch(facecolor=cmap_right(0.7), label=f'{right_team_name}')
    ]
    ax.legend(
        handles=legend_elements, 
        loc='lower center',
        bbox_to_anchor=(0.5, -0.05),
        ncol=2, 
        fontsize=9
    )

def aggregate_region_data(region_data_dict):
    region_cycles = {region: 0 for region in 'ABCDEFGHI'}
    if not region_data_dict:
        return region_cycles
    
    for player_id, regions in region_data_dict.items():
        for region_letter, region_info in regions.items():
            if region_letter in region_cycles:
                cycles = region_info.get('positionCycles', 0)
                region_cycles[region_letter] += int(cycles)
    return region_cycles
def get_passing_data(team_data):
    if not isinstance(team_data, dict):
        return {
            'length': 0,
            'width': 0,
            'true': 0,
            'wrong': 0,
            'accuracy': 0,
            'interceptions': 0
        }
    
    keys = ['passInLength', 'passinLength', 'passInWidth']
    try:
        length = team_data.get(keys[0]) or team_data.get(keys[1], 0)
        width = team_data.get(keys[2], 0)
        true = team_data.get('truePass', 0)
        wrong = team_data.get('wrongPass', 0)
        accuracy = team_data.get('passAccuracy', 0)
        interceptions = team_data.get('intercept', team_data.get('Intercept', 0))
        
        return {
            'length': length,
            'width': width,
            'true': true,
            'wrong': wrong,
            'accuracy': accuracy,
            'interceptions': interceptions
        }
    except Exception:
        return {
            'length': 0,
            'width': 0,
            'true': 0,
            'wrong': 0,
            'accuracy': 0,
            'interceptions': 0
        }

def parse_ranking_file():
    possible_paths = ['Table.txt', '../Table.txt']
    file_path = None
    
    for path in possible_paths:
        if os.path.exists(path):
            file_path = path
            break
    
    if file_path is None:
        print("\033[1;33mWarning: Ranking file not found\033[0m")
        return [], [], {}, False

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"\033[1;33mWarning: Error reading ranking file: {str(e)}\033[0m")
        return [], [], {}, False

    teams = []
    team_names = []
    match_results = {}
    
    lines = [line.strip() for line in content.split('\n') if line.strip()]
    
    # Find header line
    header_idx = -1
    for i, line in enumerate(lines):
        if 'Rank' in line and 'Points' in line and 'TGD' in line:
            header_idx = i
            break
    
    if header_idx == -1:
        print("\033[1;33mWarning: Header not found\033[0m")
        return [], [], {}, False
    
    # Process header
    header_parts = [p.strip() for p in lines[header_idx].split('|') if p.strip()]
    fixed_columns = {'Rank', 'Points', 'TGD'}
    
    # Identify fixed column indices
    fixed_indices = []
    for i, part in enumerate(header_parts):
        if part in fixed_columns:
            fixed_indices.append(i)
    
    if len(fixed_indices) < 3:
        print("\033[1;33mWarning: Couldn't identify all fixed columns\033[0m")
        return [], [], {}, False
    
    # Team names are all columns before the first fixed column
    team_names = header_parts[:fixed_indices[0]]
    
    # Process data rows
    for line in lines[header_idx+1:]:
        # Skip separator lines
        if line.startswith('+') or line.startswith('-') or line.startswith('='):
            continue
            
        parts = [p.strip() for p in line.split('|') if p.strip()]
        
        # Skip lines that don't have enough data
        if len(parts) < len(team_names) + 3:
            continue
            
        try:
            # Extract team data (first column is team name)
            row_team = parts[0]
            
            # Skip header rows
            if row_team in fixed_columns or row_team == 'Team':
                continue
                
            # Skip if team name looks like a separator
            if all(c in ['=', '-', '+'] for c in row_team):
                continue
                
            # Fixed columns are the last 3
            rank = parts[-3]
            points = parts[-2]
            tgd = parts[-1]
            
            # Results are between team name and fixed columns
            results = parts[1:1+len(team_names)]
            
            # Skip if any result looks like a separator
            if any(all(c in ['=', '-', '+'] for c in r) for r in results):
                continue
                
            teams.append({
                'team': row_team,
                'rank': rank,
                'points': points,
                'tgd': tgd
            })
            
            # Store match results
            for idx, col_team in enumerate(team_names):
                if idx < len(results) and row_team != col_team:
                    # Skip if result is a separator pattern
                    if not all(c in ['=', '-', '+'] for c in results[idx]):
                        match_results[(row_team, col_team)] = results[idx]
                    
        except Exception as e:
            print(f"\033[1;33mWarning: Error parsing line: {line} - {str(e)}\033[0m")
            continue

    has_data = len(teams) > 0
    return teams, team_names, match_results, has_data

def draw_ranking_table(ax, teams, team_names, match_results, has_data, left_team_name, right_team_name):
    ax.set_axis_off()
    
    if not has_data:
        ax.text(0.5, 0.5, "No ranking data available", 
                ha='center', va='center', fontsize=12)
        return
    
    try:
        team_width = max(max(len(team['team']) for team in teams), 7)
        result_width = 7
        rank_width = 5
        points_width = 7
        tgd_width = 5
        
        cell_text = []
        row_labels = []
        
        for team in teams:
            row_data = []
            row_labels.append(team['team'])
            
            for opponent in team_names:
                if team['team'] == opponent:
                    row_data.append('#')
                else:
                    result = match_results.get((team['team'], opponent), '-')
                    row_data.append(result)
            
            row_data.append(team['rank'])
            row_data.append(team['points'])
            row_data.append(team['tgd'])
            cell_text.append(row_data)
        
        column_labels = list(team_names) + ['Rank', 'Points', 'TGD']
        
        table = ax.table(
            cellText=cell_text,
            rowLabels=row_labels,
            colLabels=column_labels,
            cellLoc='center',
            loc='center',
            bbox=[0.1, 0.1, 0.9, 0.8]
        )
        
        # Bold specific headers
        for j, col_label in enumerate(column_labels):
            cell = table[(0, j)]  # Header row
            if col_label in ['Rank', 'Points', 'TGD']:
                cell.get_text().set_weight('bold')  # Apply bold
        
        table.auto_set_font_size(False)
        table.set_fontsize(10)
        table.scale(1, 1.5)
        
        for key, cell in table.get_celld().items():
            cell.get_text().set_color('black')
        
        light_purple = '#e6d4ff'
        
        left_idx = None
        right_idx = None
        
        for i, team in enumerate(teams):
            if team['team'] == left_team_name:
                left_idx = i
            if team['team'] == right_team_name:
                right_idx = i
        
        if left_idx is not None and right_idx is not None:
            if right_team_name in team_names:
                col_idx = team_names.index(right_team_name)
                cell = table[(left_idx+1, col_idx)]
                cell.set_facecolor(light_purple)
                cell.get_text().set_weight('bold')
            
            if left_team_name in team_names:
                col_idx = team_names.index(left_team_name)
                cell = table[(right_idx+1, col_idx)]
                cell.set_facecolor(light_purple)
                cell.get_text().set_weight('bold')
        
        for i, team in enumerate(teams):
            for j, opponent in enumerate(team_names):
                if team['team'] == opponent:
                    cell = table[(i+1, j)]
                    cell.set_facecolor('black')
                    cell.get_text().set_text('')
        
        ax.set_title('Tournament Standings', fontsize=14, pad=20, weight='bold', loc='center')
        
    except Exception as e:
        ax.text(0.5, 0.5, f"Error drawing table: {str(e)}", 
                ha='center', va='center', fontsize=12, color='red')

def plot_passing_pattern(team_data, team_name, ax):
    try:
        data = get_passing_data(team_data)
        
        if not data or (data['length'] == 0 and data['width'] == 0):
            ax.text(0.5, 0.5, "No Passing Data", ha='center', va='center', fontsize=14)
            ax.set_title(f'Passing Pattern - {team_name}', fontsize=12)
            return
        
        wedges, texts, autotexts = ax.pie(
            [data['length'], data['width']],
            labels=['Length Passes', 'Width Passes'],
            autopct=lambda p: f'{p:.1f}%\n({int(p/100*(data["length"]+data["width"]))})',
            startangle=90,
            colors=['#1f77b4', '#ff7f0e'],
            wedgeprops={'edgecolor': 'black', 'linewidth': 1},
            textprops={'fontsize': 10}
        )
        
        plt.setp(autotexts, size=10, weight='bold')
        
        title = (
            f'Passing Pattern: {team_name}\n'
            f'Correct: {data["true"]} | Wrong: {data["wrong"]}\n'
            f'Accuracy: {data["accuracy"]}% | Interceptions: {data["interceptions"]}'
        )
        ax.set_title(title, fontsize=11, pad=20)
    except Exception as e:
        ax.text(0.5, 0.5, f"Error: {str(e)}", ha='center', va='center', fontsize=12, color='red')
        ax.set_title(f'Passing Pattern - {team_name} (Error)', fontsize=12)

def plot_defensive_strengths(left_team, right_team, ax):
    try:
        left_data = get_passing_data(left_team)
        right_data = get_passing_data(right_team)
        
        teams = [left_team.get('leftTeam', 'Left Team'), 
                 right_team.get('rightTeam', 'Right Team')]
        
        interceptions = [left_data['interceptions'], right_data['interceptions']]
        colors = ['#1f77b4', '#d62728']
        
        bars = ax.bar(teams, interceptions, color=colors, edgecolor='black')
        ax.set_title('Defensive Interceptions', fontsize=14, weight='bold', pad=15)
        ax.set_ylabel('Number of Interceptions', fontsize=11)
        ax.grid(axis='y', linestyle='--', alpha=0.7)
        
        for i, bar in enumerate(bars):
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2, height/2, 
                    f'{int(height)}', ha='center', va='center', 
                    fontsize=16, weight='bold', color='white')
            
    except Exception as e:
        ax.text(0.5, 0.5, f"Error: {str(e)}", ha='center', va='center', fontsize=12, color='red')
        ax.set_title('Defensive Interceptions (Error)', fontsize=14)

def get_shooting_data(team_data):
    if not isinstance(team_data, dict):
        return {
            'on_target': 0,
            'off_target': 0,
            'accuracy': 0,
            'goals': 0
        }
    
    try:
        return {
            'on_target': team_data.get('onTargetShoot', 0),
            'off_target': team_data.get('offTarget', 0),
            'accuracy': team_data.get('shootAccuracy', 0),
            'goals': team_data.get('goals', 0)
        }
    except Exception:
        return {
            'on_target': 0,
            'off_target': 0,
            'accuracy': 0,
            'goals': 0
        }

def plot_shooting_positions(team_data, team_name, ax, is_left_team):
    try:
        data = get_shooting_data(team_data)

        summary_text = (
            f'{team_name}:\n'
            f'On Target: {data["on_target"]}\n'
            f'Off Target: {data["off_target"]}\n'
            f'Goals: {data["goals"]}\n'
            f'Accuracy: {data["accuracy"]}%'
        )

        pos_x = 20 if is_left_team else 100
        pos_y = 95

        ax.text(pos_x, pos_y, summary_text, 
                fontsize=10, color='white', weight='bold',
                bbox=dict(facecolor='#1f77b4' if is_left_team else '#d62728',
                          alpha=0.85, boxstyle='round,pad=0.4'),
                ha='center', va='top')
                
    except Exception:
        pass

def process_json_files(directory):

    teams, team_names, match_results, has_data = parse_ranking_file()
    
    for filename in os.listdir(directory):
        if filename.endswith('.json'):
            filepath = os.path.join(directory, filename)
            
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception as e:
                print(f"\033[0;31mError processing {filename}: {str(e)}\033[0m")
                continue
                
            match_name = os.path.splitext(filename)[0]
            match_dir = os.path.join(MAIN_OUTPUT_DIR, match_name)
            os.makedirs(match_dir, exist_ok=True)

            left_team = data.get('leftTeam', {})
            right_team = data.get('rightTeam', {})
            game_result = data.get('gameResult', {})
            left_region_data = aggregate_region_data(left_team.get('regionData', {}))
            right_region_data = aggregate_region_data(right_team.get('regionData', {}))
            
            left_team_name = left_team.get('leftTeam', 'Left Team')
            right_team_name = right_team.get('rightTeam', 'Right Team')
            
            left_score = game_result.get(left_team_name, 0)
            if not isinstance(left_score, (int, float)):
                left_score = 0
                
            right_score = game_result.get(right_team_name, 0)
            if not isinstance(right_score, (int, float)):
                right_score = 0
            
            try:
                fig = plt.figure(figsize=(16, 18), facecolor='#f0f0f0')
                plt.suptitle(
                    f"TACTICAL ANALYSIS: {left_team_name} {left_score}-{right_score} {right_team_name}", 
                    fontsize=20, weight='bold', y=0.97
                )
                
                plt.figtext(
                    0.5, 0.94,
                    f"Possession: {left_team.get('possession', 0)}%-{right_team.get('possession', 0)}% | "
                    f"Shots: {left_team.get('onTargetShoot', 0)+left_team.get('offTarget', 0)}-"
                    f"{right_team.get('onTargetShoot', 0)+right_team.get('offTarget', 0)} | "
                    f"Pass Accuracy: {left_team.get('passAccuracy', 0)}%-{right_team.get('passAccuracy', 0)}%",
                    ha='center', fontsize=14, color='#333333'
                )
                
                gs = fig.add_gridspec(3, 2, height_ratios=[1, 1.5, 0.8], 
                                      width_ratios=[1, 1.5], 
                                      hspace=0.15, wspace=0.15)
                
                ax1 = fig.add_subplot(gs[0, 0])
                ax2 = fig.add_subplot(gs[0, 1])
                ax3 = fig.add_subplot(gs[1, 0])
                ax4 = fig.add_subplot(gs[1, 1])
                ax5 = fig.add_subplot(gs[2, :])
                
                plot_passing_pattern(left_team, left_team_name, ax1)
                plot_passing_pattern(right_team, right_team_name, ax2)
                
                plot_defensive_strengths(left_team, right_team, ax3)
                
                draw_field(ax4)
                draw_heatmap_on_field(ax4, left_team_name, right_team_name, left_region_data, right_region_data)
                plot_shooting_positions(left_team, left_team_name, ax4, True)
                plot_shooting_positions(right_team, right_team_name, ax4, False)

                draw_ranking_table(ax5, teams, team_names, match_results, has_data, left_team_name, right_team_name)
                
                handles, labels = ax4.get_legend_handles_labels()
                unique_labels = dict(zip(labels, handles))
                if unique_labels:
                    ax4.legend(
                        unique_labels.values(), unique_labels.keys(),
                        loc='upper center', bbox_to_anchor=(0.5, -0.05),
                        ncol=2, fontsize=9, framealpha=0.8
                    )
                
                plt.figtext(
                    0.5, 0.02, 
                    f"Generated from {filename}",
                    ha='center', fontsize=10, color='#666666'
                )
                
                output_path = os.path.join(match_dir, f"{match_name}_analysis.png")
                plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor())
                plt.close()
                print(f'\033[1;33mCreated professional diagram\033[0m: \033[0;32m{output_path}\033[0m')
                
            except Exception as e:
                print(f"\033[0;31mFailed to create diagram for {filename}: {str(e)}\033[0m")
                plt.close('all')

if __name__ == "__main__":
    input_dir = 'LogsJSON'
    
    if not os.path.exists(MAIN_OUTPUT_DIR):
        os.makedirs(MAIN_OUTPUT_DIR)
        print(f"\033[1;33mCreated main output directory: {MAIN_OUTPUT_DIR}\033[0m")
    
    process_json_files(input_dir)
    print("\033[0;32mAnalysis complete! All results saved in:", MAIN_OUTPUT_DIR, "\033[0m")