#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import sqlite3
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Rectangle, Arc

FIELD_X = 52.5
FIELD_Y = 34.0
GOAL_DEPTH = 2.0
TEAM_A = '#22d3ee'
TEAM_B = '#f59e0b'
BG = '#0b1020'
PANEL = '#111827'
TEXT = '#e5e7eb'
MUTED = '#94a3b8'
GRID = '#243047'
WHITE = '#f8fafc'
SUCCESS = '#34d399'
DANGER = '#fb7185'


def connect(db_path: Path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def tournament_rows(db_path: Path, tournament_id: str):
    with connect(db_path) as conn:
        return rows(conn, """SELECT id, match_number, team1, team2, score1, score2, penalty1, penalty2, winner, status
                              FROM matches WHERE tournament_id=? AND status='completed'
                              ORDER BY COALESCE(match_number,id)""", (tournament_id,))


def rows(conn, query, params=()):
    return [dict(r) for r in conn.execute(query, params)]


def pitch(ax, dark=True, show_zones=False):
    ax.set_facecolor(BG if dark else WHITE)
    line = '#53637f' if dark else '#64748b'
    grass1 = '#0a2d26' if dark else '#dff5e9'
    grass2 = '#0b332a' if dark else '#d7efdf'
    ax.set_xlim(-FIELD_X - 5, FIELD_X + 5); ax.set_ylim(-FIELD_Y - 5, FIELD_Y + 5)
    ax.set_aspect('equal', adjustable='box'); ax.axis('off')
    for i, x0 in enumerate(range(-52, 53, 13)):
        ax.add_patch(Rectangle((x0, -FIELD_Y), 13, FIELD_Y*2, facecolor=grass1 if i%2==0 else grass2, edgecolor='none', zorder=0))
    ax.add_patch(Rectangle((-FIELD_X,-FIELD_Y),FIELD_X*2,FIELD_Y*2,fill=False,edgecolor=line,linewidth=2,zorder=2))
    ax.plot([0,0],[-FIELD_Y,FIELD_Y],color=line,linewidth=1.4,zorder=2)
    ax.add_patch(Circle((0,0),9.15,fill=False,edgecolor=line,linewidth=1.4,zorder=2)); ax.scatter([0],[0],s=15,c=line,zorder=2)
    for sx in (-1,1):
        x0=sx*FIELD_X; box_x=x0-16.5 if sx>0 else x0; small_x=x0-5.5 if sx>0 else x0
        ax.add_patch(Rectangle((box_x,-20.16),16.5,40.32,fill=False,edgecolor=line,linewidth=1.4,zorder=2))
        ax.add_patch(Rectangle((small_x,-9.16),5.5,18.32,fill=False,edgecolor=line,linewidth=1.4,zorder=2))
        ax.add_patch(Arc((x0-11*sx,0),18.3,18.3,angle=0,theta1=-53 if sx>0 else 127,theta2=53 if sx>0 else 233,color=line,linewidth=1.3,zorder=2))
        ax.add_patch(Rectangle((x0 if sx>0 else x0-GOAL_DEPTH,-3.66),GOAL_DEPTH,7.32,fill=False,edgecolor=line,linewidth=1.2,zorder=2))
    if show_zones:
        for x in (-17.5,17.5): ax.plot([x,x],[-FIELD_Y,FIELD_Y],color=WHITE,alpha=.07,linewidth=.8,zorder=1)


def draw_title(fig,title,subtitle=None):
    fig.text(.055,.955,title,color=TEXT,fontsize=20,fontweight='bold',ha='left',va='top')
    if subtitle: fig.text(.055,.925,subtitle,color=MUTED,fontsize=9,ha='left',va='top')

def panel_box(ax,x,y,w,h,face=PANEL,edge=GRID,radius=.02):
    from matplotlib.patches import FancyBboxPatch
    ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle=f"round,pad=.012,rounding_size={radius}",transform=ax.transAxes,facecolor=face,edgecolor=edge,linewidth=1))

def metric_card(ax,x,y,w,h,label,value,color):
    panel_box(ax,x,y,w,h)
    ax.text(x+.04,y+h*.62,label.upper(),transform=ax.transAxes,color=MUTED,fontsize=7,fontweight='bold')
    ax.text(x+.04,y+h*.28,value,transform=ax.transAxes,color=color,fontsize=14,fontweight='bold')

def add_header(fig, title, subtitle=None):
    fig.suptitle(title, color=TEXT, fontsize=17, fontweight='bold', x=0.06, ha='left', y=0.97)
    if subtitle:
        fig.text(0.06, 0.935, subtitle, color=MUTED, fontsize=9, ha='left')


def team_colors(teams):
    if not teams:
        return {}
    palette = [TEAM_A, TEAM_B]
    return {team: palette[i % len(palette)] for i, team in enumerate(teams)}


def generate_match_overview(db_path: Path, match_id: int, output: Path) -> Path:
    with connect(db_path) as conn:
        match = dict(conn.execute('SELECT * FROM matches WHERE id=?', (match_id,)).fetchone())
        teams = rows(conn, 'SELECT * FROM match_team_statistics WHERE match_id=? ORDER BY team', (match_id,))
        players = rows(conn, """SELECT p.team, p.unum, AVG(p.x) AS avg_x, AVG(p.y) AS avg_y
            FROM match_player_frames p WHERE p.match_id=? GROUP BY p.team, p.unum ORDER BY p.team, p.unum""", (match_id,))
    output.parent.mkdir(parents=True, exist_ok=True)
    fig = plt.figure(figsize=(16, 9), facecolor=BG)
    gs = fig.add_gridspec(1, 2, width_ratios=[1.45, 1], left=.035, right=.97, top=.88, bottom=.07, wspace=.035)
    ax_pitch = fig.add_subplot(gs[0, 0]); pitch(ax_pitch, show_zones=True)
    colors = team_colors([t['team'] for t in teams])
    if teams:
        ax_pitch.text(-50.5, 36.7, f"{teams[0]['team']}  {match.get('score1') or 0}", color=colors.get(teams[0]['team'], TEAM_A), fontsize=11, fontweight='bold')
        ax_pitch.text(18, 36.7, f"{teams[1]['team']}  {match.get('score2') or 0}", color=colors.get(teams[1]['team'], TEAM_B), fontsize=11, fontweight='bold')
    for p in players:
        c = colors.get(p['team'], TEAM_A)
        x, y = float(p['avg_x'] or 0), float(p['avg_y'] or 0)
        ax_pitch.scatter([x], [y], s=520, c=c, marker='o', edgecolors=BG, linewidths=2.5, zorder=4, alpha=.96)
        ax_pitch.scatter([x], [y], s=610, facecolors='none', edgecolors=WHITE, linewidths=.55, zorder=5, alpha=.30)
        ax_pitch.text(x, y, str(p['unum']), color=BG, ha='center', va='center', fontsize=9, fontweight='bold', zorder=6)
    ax_pitch.set_title('Average shape', color=TEXT, loc='left', fontsize=14, fontweight='bold', pad=18)

    ax = fig.add_subplot(gs[0, 1]); ax.set_facecolor(BG); ax.axis('off')
    title=f"{match['team1']}   {match.get('score1') or 0}  —  {match.get('score2') or 0}   {match['team2']}"
    ax.text(0.0, 0.95, title, color=TEXT, fontsize=16, fontweight='bold', transform=ax.transAxes)
    ax.text(0.0, 0.905, f"Winner · {match.get('winner') or 'Draw'}", color=MUTED, fontsize=9, transform=ax.transAxes)
    if teams:
        a,b=teams[0],teams[1]
        metric_card(ax, 0.0, 0.75, 0.47, 0.11, 'Possession', f"{float(a.get('possession_pct') or 0):.1f}%", colors.get(a['team'], TEAM_A))
        metric_card(ax, 0.51, 0.75, 0.47, 0.11, 'Possession', f"{float(b.get('possession_pct') or 0):.1f}%", colors.get(b['team'], TEAM_B))
        metric_card(ax, 0.0, 0.61, 0.47, 0.11, 'Passes', f"{int(a.get('passes_completed') or 0)}", colors.get(a['team'], TEAM_A))
        metric_card(ax, 0.51, 0.61, 0.47, 0.11, 'Passes', f"{int(b.get('passes_completed') or 0)}", colors.get(b['team'], TEAM_B))
        metric_card(ax, 0.0, 0.47, 0.47, 0.11, 'Shots', f"{int(a.get('shots') or 0)}", colors.get(a['team'], TEAM_A))
        metric_card(ax, 0.51, 0.47, 0.47, 0.11, 'Shots', f"{int(b.get('shots') or 0)}", colors.get(b['team'], TEAM_B))
        metric_card(ax, 0.0, 0.33, 0.47, 0.11, 'Territory', f"{float(a.get('avg_territory') or 0)*100:.1f}%", colors.get(a['team'], TEAM_A))
        metric_card(ax, 0.51, 0.33, 0.47, 0.11, 'Territory', f"{float(b.get('avg_territory') or 0)*100:.1f}%", colors.get(b['team'], TEAM_B))
        metric_card(ax, 0.0, 0.19, 0.47, 0.11, 'Space', f"{float(a.get('avg_space_control') or 0)*100:.1f}%", colors.get(a['team'], TEAM_A))
        metric_card(ax, 0.51, 0.19, 0.47, 0.11, 'Space', f"{float(b.get('avg_space_control') or 0)*100:.1f}%", colors.get(b['team'], TEAM_B))
        metric_card(ax, 0.0, 0.05, 0.47, 0.11, 'Pressure', f"{float(a.get('avg_ball_pressure') or 0):.3f}", colors.get(a['team'], TEAM_A))
        metric_card(ax, 0.51, 0.05, 0.47, 0.11, 'Pressure', f"{float(b.get('avg_ball_pressure') or 0):.3f}", colors.get(b['team'], TEAM_B))
    draw_title(fig, 'Match overview', 'Runner Analytics · analytics · average shape + match pulse')
    fig.savefig(output, dpi=170, facecolor=BG)
    plt.close(fig)
    return output


def shot_rows(db_path: Path, match_id: int):
    with connect(db_path) as conn:
        return rows(conn, '''
            SELECT event_type, team, unum, x, y, cycle, confidence, details_json
            FROM match_data_events
            WHERE match_id=? AND event_type IN ('shot','goal')
            ORDER BY cycle
        ''', (match_id,))


def generate_shot_map(db_path: Path, match_id: int, output: Path) -> Path:
    with connect(db_path) as conn:
        match = dict(conn.execute('SELECT * FROM matches WHERE id=?', (match_id,)).fetchone())
    events = shot_rows(db_path, match_id)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig = plt.figure(figsize=(15, 8.6), facecolor=BG)
    gs=fig.add_gridspec(1,2,width_ratios=[1.55,.55],left=.04,right=.97,top=.88,bottom=.08,wspace=.035)
    ax=fig.add_subplot(gs[0,0]); pitch(ax, show_zones=True)
    colors={match['team1']:TEAM_A,match['team2']:TEAM_B}
    totals=defaultdict(int); goals=defaultdict(int)
    for e in events:
        x=float(e.get('x') or 0); y=float(e.get('y') or 0); team=e.get('team'); c=colors.get(team,WHITE); goal=e['event_type']=='goal'; totals[team]+=1; goals[team]+=int(goal)
        if goal:
            ax.scatter([x],[y],marker='*',s=420,c=c,edgecolors=WHITE,linewidths=1.2,zorder=6)
            ax.scatter([x],[y],marker='o',s=620,facecolors='none',edgecolors=c,alpha=.22,linewidths=2,zorder=5)
        else:
            ax.scatter([x],[y],marker='X',s=115,c=c,edgecolors=BG,linewidths=.8,zorder=5)
        if e.get('unum'):
            ax.text(x+1.3,y+1.0,f"#{e['unum']}",color=c,fontsize=7,fontweight='bold',zorder=7)
    ax.text(-52.5,36.8,f"{match['team1']}  {match.get('score1') or 0}",color=TEAM_A,fontsize=10,fontweight='bold')
    ax.text(23,36.8,f"{match['team2']}  {match.get('score2') or 0}",color=TEAM_B,fontsize=10,fontweight='bold')
    right=fig.add_subplot(gs[0,1]); right.set_facecolor(BG); right.axis('off')
    right.text(0,0.93,'Attacking output',color=TEXT,fontsize=14,fontweight='bold',transform=right.transAxes)
    for i,team in enumerate([match['team1'],match['team2']]):
        y=.80-i*.32; c=colors[team]
        right.text(0,y+0.07,team,color=c,fontsize=11,fontweight='bold',transform=right.transAxes)
        right.text(0,y-0.02,f"{totals[team]} shots",color=TEXT,fontsize=18,fontweight='bold',transform=right.transAxes)
        right.text(0,y-0.09,f"{goals[team]} goals",color=MUTED,fontsize=9,transform=right.transAxes)
        right.add_patch(Rectangle((0,y-0.17),.92,.028,transform=right.transAxes,facecolor='#172238',edgecolor='none',zorder=0))
        prog=min(1.0, goals[team]/max(1,totals[team]))
        right.add_patch(Rectangle((0,y-0.17),.92*prog,.028,transform=right.transAxes,facecolor=c,edgecolor='none',zorder=1))
    right.text(0,0.12,'✕  shot     ★  goal',color=MUTED,fontsize=9,transform=right.transAxes)
    right.text(0,0.06,'Marker label = shooter number',color=MUTED,fontsize=8,transform=right.transAxes)
    draw_title(fig, f"{match['team1']}  {match.get('score1') or 0}  —  {match.get('score2') or 0}  {match['team2']}", 'Runner Analytics · analytics · shot locations and goal events')
    fig.savefig(output,dpi=170,facecolor=BG); plt.close(fig); return output


def generate_passing_network(db_path: Path, match_id: int, output: Path) -> Path:
    with connect(db_path) as conn:
        match=dict(conn.execute('SELECT * FROM matches WHERE id=?',(match_id,)).fetchone())
        events=rows(conn,"SELECT * FROM match_data_events WHERE match_id=? AND event_type='pass' ORDER BY cycle",(match_id,))
        positions=rows(conn,"""SELECT team, unum, AVG(x) AS x, AVG(y) AS y FROM match_player_frames WHERE match_id=? GROUP BY team, unum""",(match_id,))
    pos={(r['team'],int(r['unum'])):(float(r['x']),float(r['y'])) for r in positions}
    edges=defaultdict(int)
    for e in events:
        team=e.get('team'); unum=e.get('unum')
        if not team or unum is None: continue
        try:d=json.loads(e.get('details_json') or '{}')
        except json.JSONDecodeError:d={}
        rt,ru=d.get('receiver_team'),d.get('receiver_unum')
        if rt and ru is not None and rt==team: edges[(team,int(unum),rt,int(ru))]+=1
    output.parent.mkdir(parents=True,exist_ok=True)
    fig=plt.figure(figsize=(15,8.8),facecolor=BG)
    gs=fig.add_gridspec(1,2,width_ratios=[1.6,.5],left=.04,right=.97,top=.88,bottom=.07,wspace=.03)
    ax=fig.add_subplot(gs[0,0]); pitch(ax,show_zones=True)
    colors={match['team1']:TEAM_A,match['team2']:TEAM_B}
    inv=defaultdict(int)
    for (st,su,dt,du),w in edges.items(): inv[(st,su)]+=w; inv[(dt,du)]+=w
    ranked=sorted(edges.items(),key=lambda kv:kv[1])
    for (st,su,dt,du),w in ranked:
        p1,p2=pos.get((st,su)),pos.get((dt,du))
        if not p1 or not p2: continue
        c=colors.get(st,WHITE); dx=p2[0]-p1[0]; dy=p2[1]-p1[1]; length=max(1,(dx*dx+dy*dy)**.5); ox=-dy/length*1.4; oy=dx/length*1.4
        ax.annotate('',xy=(p2[0]+ox,p2[1]+oy),xytext=(p1[0]+ox,p1[1]+oy),arrowprops=dict(arrowstyle='-|>',color=c,alpha=.22+min(.58,w*.08),lw=.8+min(4.6,w*.55),shrinkA=12,shrinkB=12,connectionstyle='arc3,rad=0.03'))
        if w>=2:
            mx,my=(p1[0]+p2[0])/2+ox,(p1[1]+p2[1])/2+oy
            ax.text(mx,my,str(w),color=TEXT,fontsize=7,ha='center',va='center',zorder=8,bbox=dict(boxstyle='round,pad=.15',fc=BG,ec='none',alpha=.85))
    for (team,unum),(x,y) in pos.items():
        c=colors.get(team,WHITE); size=260+min(1300,inv.get((team,unum),0)*90)
        ax.scatter([x],[y],s=size,c=c,edgecolors=BG,linewidths=2.2,zorder=8)
        ax.scatter([x],[y],s=size*.92,facecolors='none',edgecolors=WHITE,linewidths=.45,alpha=.25,zorder=9)
        ax.text(x,y,str(unum),color=BG,fontsize=8,fontweight='bold',ha='center',va='center',zorder=10)
    ax.text(-52.5,36.8,'Node size = passing involvement · arrow = direction',color=MUTED,fontsize=8)
    right=fig.add_subplot(gs[0,1]); right.set_facecolor(BG); right.axis('off')
    right.text(0,0.93,'Passing pulse',color=TEXT,fontsize=14,fontweight='bold',transform=right.transAxes)
    pairs=sorted(edges.items(),key=lambda kv:kv[1],reverse=True)[:8]
    right.text(0,.86,f"{len(edges)} lanes · {sum(edges.values())} inferred passes",color=MUTED,fontsize=9,transform=right.transAxes)
    y=.77
    maxw=max([p[1] for p in pairs],default=1)
    for (st,su,dt,du),w in pairs:
        c=colors.get(st,WHITE); right.text(0,y,f"#{su} → #{du}",color=TEXT,fontsize=9,fontweight='bold',transform=right.transAxes)
        right.text(.88,y,str(w),color=c,fontsize=10,fontweight='bold',ha='right',transform=right.transAxes)
        right.add_patch(Rectangle((0,y-.045),.88,.012,transform=right.transAxes,facecolor='#172238',edgecolor='none'))
        right.add_patch(Rectangle((0,y-.045),.88*min(1,w/maxw),.012,transform=right.transAxes,facecolor=c,edgecolor='none'))
        y-=.09
    right.text(0,.08,'Same-team inferred links only.',color=MUTED,fontsize=8,transform=right.transAxes)
    draw_title(fig,'Passing network',f"{match['team1']} vs {match['team2']} · pitch-positioned lanes")
    fig.savefig(output,dpi=170,facecolor=BG); plt.close(fig); return output


def generate_tournament_results(db_path: Path, tournament_id: str, output: Path) -> Path:
    rows_ = tournament_rows(db_path, tournament_id)
    stats = defaultdict(lambda: {'W': 0, 'D': 0, 'L': 0, 'GF': 0})
    for m in rows_:
        a, b = m['team1'], m['team2']; winner = m.get('winner')
        stats[a]['GF'] += int(m.get('score1') or 0); stats[b]['GF'] += int(m.get('score2') or 0)
        if winner:
            loser = b if winner == a else a
            stats[winner]['W'] += 1; stats[loser]['L'] += 1
        else:
            stats[a]['D'] += 1; stats[b]['D'] += 1
    teams = sorted(stats, key=lambda t: (-stats[t]['W'], -stats[t]['GF'], t))
    fig, ax = plt.subplots(figsize=(13, 7), facecolor=BG)
    ax.set_facecolor(BG)
    x = list(range(len(teams)))
    w = [stats[t]['W'] for t in teams]; d = [stats[t]['D'] for t in teams]; l = [stats[t]['L'] for t in teams]
    ax.bar(x, w, color=TEAM_A, label='Wins')
    ax.bar(x, d, bottom=w, color='#a78bfa', label='Draws')
    ax.bar(x, l, bottom=[i+j for i,j in zip(w,d)], color=DANGER, label='Losses')
    ax.set_xticks(x, teams, rotation=18, ha='right', color=TEXT)
    ax.tick_params(colors=MUTED)
    ax.spines[:].set_visible(False)
    ax.grid(axis='y', color=GRID, linewidth=0.7, alpha=0.7)
    ax.set_axisbelow(True)
    ax.set_ylabel('Matches', color=MUTED)
    ax.legend(facecolor=PANEL, edgecolor='none', labelcolor=TEXT)
    ax.set_title('Tournament Results', color=TEXT, loc='left', fontsize=15, fontweight='bold')
    fig.text(0.06, 0.93, tournament_id, color=MUTED, fontsize=9)
    fig.tight_layout(pad=2)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=160, facecolor=BG)
    plt.close(fig)
    return output


def generate_tournament_network(db_path: Path, tournament_id: str, output: Path) -> Path:
    rows_ = tournament_rows(db_path, tournament_id)
    teams = sorted({m['team1'] for m in rows_} | {m['team2'] for m in rows_})
    angle_step = 2 * math.pi / max(1, len(teams))
    coords = {t: (22 * math.cos(i * angle_step), 22 * math.sin(i * angle_step)) for i, t in enumerate(teams)}
    fig, ax = plt.subplots(figsize=(13, 9), facecolor=BG)
    pitch(ax, dark=True)
    # For a tournament network, use a neutral canvas rather than a full pitch.
    ax.cla(); ax.set_facecolor(BG); ax.axis('off'); ax.set_aspect('equal')
    colors = {t: [TEAM_A, TEAM_B][i % 2] for i, t in enumerate(teams)}
    for m in rows_:
        a, b = m['team1'], m['team2']; winner = m.get('winner')
        if a not in coords or b not in coords: continue
        x1, y1 = coords[a]; x2, y2 = coords[b]
        if winner == a:
            c = TEAM_A
        elif winner == b:
            c = TEAM_B
        else:
            c = '#64748b'
        ax.annotate('', xy=(x2, y2), xytext=(x1, y1), arrowprops=dict(arrowstyle='-|>', color=c, lw=1.8, alpha=0.72))
        ax.text((x1+x2)/2, (y1+y2)/2, f"{m.get('score1',0)}–{m.get('score2',0)}", color=MUTED, fontsize=7,
                bbox=dict(boxstyle='round,pad=0.15', fc=PANEL, ec='none', alpha=0.85))
    for t, (x, y) in coords.items():
        ax.scatter([x], [y], s=1500, c=colors[t], edgecolors=WHITE, linewidths=1.4)
        ax.text(x, y, t, color=BG, ha='center', va='center', fontsize=10, fontweight='bold', wrap=True)
    ax.set_xlim(-30, 30); ax.set_ylim(-27, 27)
    ax.set_title('Tournament Match Network', color=TEXT, loc='left', fontsize=15, fontweight='bold')
    ax.text(-30, 24.5, 'Arrow points toward the winner · gray = draw', color=MUTED, fontsize=9)
    fig.tight_layout(pad=2)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=160, facecolor=BG)
    plt.close(fig)
    return output


def generate_match_graphics(db_path: Path, match_id: int, output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    files = {
        'overview': generate_match_overview(db_path, match_id, output_dir / 'match_overview.png'),
        'shots': generate_shot_map(db_path, match_id, output_dir / 'shot_map.png'),
        'passing': generate_passing_network(db_path, match_id, output_dir / 'passing_network.png'),
    }
    return {k: str(v) for k, v in files.items()}


def generate_tournament_graphics(db_path: Path, tournament_id: str, output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    files = {
        'results': generate_tournament_results(db_path, tournament_id, output_dir / 'results_wdl.png'),
        'network': generate_tournament_network(db_path, tournament_id, output_dir / 'tournament_network.png'),
    }
    return {k: str(v) for k, v in files.items()}


def main():
    parser = argparse.ArgumentParser(description='Runner report graphics generator')
    parser.add_argument('--db', required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--match-id', type=int)
    group.add_argument('--tournament-id')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    if args.match_id:
        print(json.dumps(generate_match_graphics(Path(args.db), args.match_id, Path(args.output)), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(generate_tournament_graphics(Path(args.db), args.tournament_id, Path(args.output)), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
