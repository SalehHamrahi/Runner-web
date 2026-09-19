from __future__ import annotations

import csv
import json
import math
import re
import shutil
from collections import defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable

FIELD_X = 52.5
FIELD_Y = 34.0
GOAL_Y = 7.32
POSSESSION_DISTANCE = 2.5
RECEIVE_DISTANCE = 3.0
PASS_WINDOW = 40
SHOT_MIN_SPEED = 1.5


@dataclass
class BallFrame:
    match_id: int
    cycle: int
    playmode: str | None
    left_score: int | None
    right_score: int | None
    x: float
    y: float
    vx: float
    vy: float


@dataclass
class PlayerFrame:
    match_id: int
    cycle: int
    side: str
    team: str
    unum: int
    player_type: int | None
    state: str | None
    x: float
    y: float
    vx: float
    vy: float
    body: float | None = None
    neck: float | None = None
    focus_x: float | None = None
    focus_y: float | None = None
    stamina: float | None = None
    effort: float | None = None
    recovery: float | None = None
    capacity: float | None = None
    kick_count: int | None = None
    counters: list[Any] | None = None


@dataclass
class MatchAction:
    match_id: int
    cycle: int
    subcycle: int
    team: str
    unum: int
    action_type: str
    raw_action: str
    args: list[str]
    attention_side: str | None = None
    attention_unum: int | None = None
    say_text: str | None = None


@dataclass
class MatchEvent:
    match_id: int
    cycle: int
    event_type: str
    team: str | None
    unum: int | None
    x: float | None
    y: float | None
    confidence: str
    details: dict[str, Any]


def _num(value: Any, default: float | None = None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int | None = None) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def tokenize_sexpr(text: str) -> list[str]:
    return re.findall(r'\(|\)|"(?:\\.|[^"\\])*"|[^\s()]+', text)


def parse_sexpr(text: str) -> Any:
    tokens = tokenize_sexpr(text)
    index = 0

    def parse() -> Any:
        nonlocal index
        if index >= len(tokens):
            raise ValueError("Unexpected end of S-expression")
        token = tokens[index]
        index += 1
        if token == '(':
            result = []
            while index < len(tokens) and tokens[index] != ')':
                result.append(parse())
            if index >= len(tokens):
                raise ValueError("Unclosed S-expression")
            index += 1
            return result
        if token == ')':
            raise ValueError("Unexpected closing parenthesis")
        if len(token) >= 2 and token[0] == '"' and token[-1] == '"':
            return bytes(token[1:-1], 'utf-8').decode('unicode_escape')
        try:
            if re.fullmatch(r'-?\d+', token):
                return int(token)
            return float(token)
        except ValueError:
            return token

    value = parse()
    if index != len(tokens):
        raise ValueError("Trailing tokens in S-expression")
    return value


def iter_expressions(path: Path) -> Iterable[str]:
    data = path.read_bytes().decode('utf-8', errors='ignore')
    depth = 0
    start = None
    in_string = False
    escaped = False
    for i, char in enumerate(data):
        if in_string:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == '(':
            if depth == 0:
                start = i
            depth += 1
        elif char == ')' and depth:
            depth -= 1
            if depth == 0 and start is not None:
                yield data[start:i + 1]
                start = None


def iter_show_expressions(path: Path) -> Iterable[str]:
    for expression in iter_expressions(path):
        if expression.startswith('(show '):
            yield expression

def _nested_items(expr: Any) -> Iterable[list[Any]]:
    if isinstance(expr, list):
        for item in expr:
            if isinstance(item, list):
                yield item
                yield from _nested_items(item)


def _find_first_simple_tag(expr: Any, tag: str) -> list[Any] | None:
    for item in _nested_items(expr):
        if item and item[0] == tag:
            return item
    return None


def _find_ball(expr: Any) -> tuple[float, float, float, float] | None:
    for item in _nested_items(expr):
        # ((b) X Y VX VY) becomes [ ['b'], X, Y, VX, VY ].
        if len(item) == 5 and isinstance(item[0], list) and item[0] == ['b']:
            values = [_num(v) for v in item[1:5]]
            if all(v is not None for v in values):
                return values[0], values[1], values[2], values[3]
    return None


def _parse_player(node: list[Any], left_team: str, right_team: str, match_id: int, cycle: int) -> PlayerFrame | None:
    if len(node) < 9 or not isinstance(node[0], list):
        return None
    identity = node[0]
    if len(identity) < 2 or str(identity[0]).lower() not in {'l', 'r'}:
        return None
    side = str(identity[0]).lower()
    unum = _int(identity[1])
    if unum is None:
        return None

    player_type = _int(node[1]) if len(node) > 1 else None
    state = str(node[2]) if len(node) > 2 else None
    x, y, vx, vy = (_num(node[i]) for i in range(3, 7))
    if None in (x, y, vx, vy):
        return None
    body = _num(node[7]) if len(node) > 7 else None
    neck = _num(node[8]) if len(node) > 8 else None
    focus_x = focus_y = None
    stamina = effort = recovery = capacity = None
    kick_count = None
    counters = None
    for item in node[9:]:
        if not isinstance(item, list) or not item:
            continue
        tag = item[0]
        if tag == 'fp' and len(item) >= 3:
            focus_x = _num(item[1])
            focus_y = _num(item[2])
        elif tag == 's':
            stamina = _num(item[1]) if len(item) > 1 else None
            effort = _num(item[2]) if len(item) > 2 else None
            recovery = _num(item[3]) if len(item) > 3 else None
            capacity = _num(item[4]) if len(item) > 4 else None
        elif tag == 'c':
            counters = list(item[1:])
            kick_count = _int(item[1]) if len(item) > 1 else None
    team = left_team if side == 'l' else right_team
    return PlayerFrame(match_id, cycle, side, team, unum, player_type, state, x, y, vx, vy, body, neck, focus_x, focus_y, stamina, effort, recovery, capacity, kick_count, counters)


def _parse_show(expr: list[Any], match_id: int, team_names: dict[str, str]) -> tuple[BallFrame | None, list[PlayerFrame], str | None, tuple[int | None, int | None]]:
    if not expr or expr[0] != 'show':
        return None, [], None, (None, None)
    cycle = _int(expr[1]) if len(expr) > 1 else None
    if cycle is None:
        return None, [], None, (None, None)

    playmode = None
    pm = _find_first_simple_tag(expr, 'pm')
    if pm and len(pm) > 1:
        playmode = str(pm[1])

    tm = _find_first_simple_tag(expr, 'tm')
    left_score = right_score = None
    if tm and len(tm) >= 5:
        team_names['l'] = str(tm[1])
        team_names['r'] = str(tm[2])
        left_score = _int(tm[3])
        right_score = _int(tm[4])

    ball_values = _find_ball(expr)
    if ball_values is None:
        return None, [], playmode, (left_score, right_score)
    bx, by, bvx, bvy = ball_values
    ball = BallFrame(match_id, cycle, playmode, left_score, right_score, bx, by, bvx, bvy)

    players: list[PlayerFrame] = []
    left_team = team_names.get('l', 'Left')
    right_team = team_names.get('r', 'Right')
    # Player records are direct children shaped as ((side unum) type state ...).
    for item in expr[2:]:
        if not isinstance(item, list) or not item or not isinstance(item[0], list):
            continue
        player = _parse_player(item, left_team, right_team, match_id, cycle)
        if player:
            players.append(player)
    return ball, players, playmode, (left_score, right_score)


def parse_rcg(path: Path, match_id: int, left_team: str | None = None, right_team: str | None = None) -> tuple[list[BallFrame], list[PlayerFrame], list[MatchEvent]]:
    team_names = {'l': left_team or 'Left', 'r': right_team or 'Right'}
    # Some RCG writers can emit more than one show record for the same cycle
    # (for example when fullstate data is present). Keep one canonical ball
    # frame per cycle and one canonical player frame per (cycle, side, unum).
    ball_by_cycle: dict[int, BallFrame] = {}
    player_by_key: dict[tuple[int, str, int], PlayerFrame] = {}
    raw_events: list[MatchEvent] = []
    previous_scores = (None, None)
    previous_playmode = None
    previous_kicks: dict[tuple[str, int], int] = {}
    current_playmode: str | None = None
    current_scores = (None, None)
    last_playmode_event: tuple[int, str] | None = None
    goal_keys: set[tuple[int, str]] = set()

    for raw in iter_expressions(path):
        try:
            expr = parse_sexpr(raw)
        except ValueError:
            continue
        if not isinstance(expr, list) or not expr:
            continue
        tag = expr[0]

        if tag == 'playmode':
            cycle = _int(expr[1]) if len(expr) > 1 else None
            mode = str(expr[2]) if len(expr) > 2 else None
            if cycle is not None and mode:
                current_playmode = mode
                if last_playmode_event != (cycle, mode):
                    raw_events.append(MatchEvent(match_id, cycle, 'playmode', None, None, None, None, 'high', {'playmode': mode}))
                    last_playmode_event = (cycle, mode)
            continue

        if tag == 'team':
            cycle = _int(expr[1]) if len(expr) > 1 else None
            if cycle is not None and len(expr) >= 6:
                team_names['l'] = str(expr[2])
                team_names['r'] = str(expr[3])
                new_scores = (_int(expr[4]), _int(expr[5]))
                current_scores = new_scores
                if all(v is not None for v in new_scores) and previous_scores[0] is not None:
                    if new_scores[0] > previous_scores[0]:
                        goal_keys.add((cycle, team_names['l']))
                        raw_events.append(MatchEvent(match_id, cycle, 'goal', team_names['l'], None, None, None, 'high', {'score': [*new_scores], 'source': 'team_record'}))
                    if new_scores[1] > previous_scores[1]:
                        goal_keys.add((cycle, team_names['r']))
                        raw_events.append(MatchEvent(match_id, cycle, 'goal', team_names['r'], None, None, None, 'high', {'score': [*new_scores], 'source': 'team_record'}))
                previous_scores = new_scores
            continue

        if tag != 'show':
            continue

        ball, frame_players, show_playmode, show_score = _parse_show(expr, match_id, team_names)
        if show_playmode:
            current_playmode = show_playmode
        if show_score != (None, None):
            current_scores = show_score
        if ball:
            ball.playmode = current_playmode
            ball.left_score, ball.right_score = current_scores
            # Last observation for a cycle wins; all observations remain represented
            # in the event stream, while the frame tables stay one-row-per-cycle.
            ball_by_cycle[ball.cycle] = ball
        for player in frame_players:
            player_by_key[(player.cycle, player.side, player.unum)] = player

        if ball and current_playmode and current_playmode != previous_playmode:
            raw_events.append(MatchEvent(match_id, ball.cycle, 'playmode', None, None, ball.x, ball.y, 'high', {'playmode': current_playmode}))
            if current_playmode in {'goal_l', 'goal_r'}:
                goal_team = team_names['l'] if current_playmode == 'goal_l' else team_names['r']
                if (ball.cycle, goal_team) not in goal_keys:
                    goal_keys.add((ball.cycle, goal_team))
                    raw_events.append(MatchEvent(match_id, ball.cycle, 'goal', goal_team, None, ball.x, ball.y, 'high', {'source': 'playmode'}))
            previous_playmode = current_playmode

        for p in frame_players:
            if p.kick_count is None:
                continue
            key = (p.side, p.unum)
            old = previous_kicks.get(key)
            if old is not None and p.kick_count > old:
                raw_events.append(MatchEvent(match_id, p.cycle, 'kick', p.team, p.unum, p.x, p.y, 'high', {
                    'kick_count_from': old,
                    'kick_count_to': p.kick_count,
                    'ball_x': ball.x if ball else None,
                    'ball_y': ball.y if ball else None,
                    'ball_vx': ball.vx if ball else None,
                    'ball_vy': ball.vy if ball else None,
                }))
            previous_kicks[key] = p.kick_count

    # Return deterministic cycle ordering regardless of how the RCG records were
    # emitted. This prevents UNIQUE(match_id, cycle) violations downstream.
    balls = [ball_by_cycle[cycle] for cycle in sorted(ball_by_cycle)]
    players = [player_by_key[key] for key in sorted(player_by_key)]
    return balls, players, raw_events


def _split_command_group(text: str) -> list[str]:
    commands=[]
    depth=0
    start=None
    in_string=False
    escaped=False
    for i,ch in enumerate(text):
        if in_string:
            if escaped: escaped=False
            elif ch=='\\': escaped=True
            elif ch=='"': in_string=False
            continue
        if ch=='"':
            in_string=True
        elif ch=='(':
            if depth==0: start=i
            depth+=1
        elif ch==')' and depth:
            depth-=1
            if depth==0 and start is not None:
                commands.append(text[start:i+1])
                start=None
    return commands


def parse_action_tokens(command: str) -> tuple[str, list[str]]:
    command=command.strip()
    if not command.startswith('(') or not command.endswith(')'):
        return command, []
    inner=command[1:-1].strip()
    parts=[]
    current=''; in_string=False; escaped=False
    for ch in inner:
        if in_string:
            current+=ch
            if escaped: escaped=False
            elif ch=='\\': escaped=True
            elif ch=='"': in_string=False
        elif ch=='"':
            in_string=True; current+=ch
        elif ch.isspace():
            if current:
                parts.append(current); current=''
        else:
            current+=ch
    if current: parts.append(current)
    return (parts[0], parts[1:]) if parts else ('', [])


def parse_rcl(path: Path, match_id: int, team_aliases: dict[str, str] | None = None) -> list[MatchAction]:
    aliases=team_aliases or {}
    actions: list[MatchAction]=[]
    line_re=re.compile(r'^(?P<cycle>\d+),(?P<sub>\d+)\s+Recv\s+(?P<agent>[^:]+):\s*(?P<body>.*)$')
    agent_re=re.compile(r'^(?P<name>.+)_(?P<unum>\d+)$')
    for raw_line in path.read_text(encoding='utf-8', errors='ignore').splitlines():
        m=line_re.match(raw_line)
        if not m:
            continue
        cycle=int(m.group('cycle')); subcycle=int(m.group('sub')); agent=m.group('agent').strip(); body=m.group('body')
        am=agent_re.match(agent)
        if not am:
            continue
        raw_team=am.group('name'); unum=int(am.group('unum'))
        team=aliases.get(raw_team, raw_team)
        for command in _split_command_group(body):
            action,args=parse_action_tokens(command)
            if not action or action in {'done'}:
                continue
            attention_side=None; attention_unum=None; say_text=None
            if action=='attentionto' and args:
                if args[0] in {'our','opp'}:
                    attention_side=args[0]
                    attention_unum=_int(args[1]) if len(args)>1 else None
                elif args[0]=='off':
                    attention_side='off'
            if action=='say' and args:
                say_text=args[0].strip('"')
            actions.append(MatchAction(match_id, cycle, subcycle, team, unum, action, command, args, attention_side, attention_unum, say_text))
    return actions



def attack_direction(cycle: int, side: str) -> float:
    first_half = cycle < 3000
    if side == 'l':
        return 1.0 if first_half else -1.0
    return -1.0 if first_half else 1.0


def nearest_player(ball: BallFrame, players: list[PlayerFrame], max_distance: float = POSSESSION_DISTANCE) -> PlayerFrame | None:
    best = None
    best_distance = max_distance
    for player in players:
        distance = math.hypot(player.x - ball.x, player.y - ball.y)
        if distance <= best_distance:
            best = player
            best_distance = distance
    return best


def _players_by_cycle(players: list[PlayerFrame]) -> dict[int, list[PlayerFrame]]:
    grouped: dict[int, list[PlayerFrame]] = defaultdict(list)
    for player in players:
        grouped[player.cycle].append(player)
    return grouped


def _ball_by_cycle(balls: list[BallFrame]) -> dict[int, BallFrame]:
    return {ball.cycle: ball for ball in balls}


def _region(x: float, y: float) -> str:
    col = 0 if x < -17.5 else 1 if x < 17.5 else 2
    row = 0 if y > 11.33 else 1 if y > -11.33 else 2
    return 'ABCDEFGHI'[row * 3 + col]


def _team_pressure(ball: BallFrame, opponents: list[PlayerFrame]) -> float:
    return sum(math.exp(-math.hypot(p.x - ball.x, p.y - ball.y) / 8.0) for p in opponents)


def _space_metrics(players: list[PlayerFrame], grid_x: int = 15, grid_y: int = 9) -> tuple[float, float]:
    left = [p for p in players if p.side == 'l']
    right = [p for p in players if p.side == 'r']
    if not left or not right:
        return 0.5, 0.0
    left_control = 0
    margin_sum = 0.0
    total = grid_x * grid_y
    for ix in range(grid_x):
        x = -FIELD_X + (ix + 0.5) * (2 * FIELD_X / grid_x)
        for iy in range(grid_y):
            y = -FIELD_Y + (iy + 0.5) * (2 * FIELD_Y / grid_y)
            dl = min(math.hypot(p.x - x, p.y - y) for p in left)
            dr = min(math.hypot(p.x - x, p.y - y) for p in right)
            if dl < dr:
                left_control += 1
            margin_sum += abs(dl - dr)
    return left_control / total, margin_sum / total


def _find_side(players: list[PlayerFrame], team: str, unum: int, cycle: int) -> str | None:
    for p in players:
        if p.team == team and p.unum == unum and p.cycle == cycle:
            return p.side
    return None


def derive_events_and_spatial(match_id: int, balls: list[BallFrame], players: list[PlayerFrame], raw_events: list[MatchEvent], grid_x: int = 15, grid_y: int = 9) -> tuple[list[dict[str, Any]], list[MatchEvent], list[MatchEvent]]:
    p_by_cycle = _players_by_cycle(players)
    b_by_cycle = _ball_by_cycle(balls)
    spatial: list[dict[str, Any]] = []
    derived_events = list(raw_events)

    for ball in balls:
        ps = p_by_cycle.get(ball.cycle, [])
        possessor = nearest_player(ball, ps)
        left = [p for p in ps if p.side == 'l']
        right = [p for p in ps if p.side == 'r']
        left_space, control_margin = _space_metrics(ps, grid_x, grid_y)
        spatial.append({
            'match_id': match_id,
            'cycle': ball.cycle,
            'ball_x': ball.x,
            'ball_y': ball.y,
            'region': _region(ball.x, ball.y),
            'possession_team': possessor.team if possessor else None,
            'possession_unum': possessor.unum if possessor else None,
            'possession_confidence': 'medium' if possessor else 'none',
            'left_ball_pressure': _team_pressure(ball, right),
            'right_ball_pressure': _team_pressure(ball, left),
            'left_territory': sum(1 for p in left if p.x > 0) / max(1, len(left)),
            'right_territory': sum(1 for p in right if p.x < 0) / max(1, len(right)),
            'left_space_control': left_space,
            'right_space_control': 1.0 - left_space,
            'space_control_margin': control_margin,
        })

    kick_events = [event for event in raw_events if event.event_type == 'kick']
    goal_events = [event for event in raw_events if event.event_type == 'goal']
    for kick in kick_events:
        ball = b_by_cycle.get(kick.cycle)
        if not ball:
            continue
        side = _find_side(players, kick.team or '', kick.unum or -1, kick.cycle) or 'l'
        vx = _num(kick.details.get('ball_vx'), 0.0) or 0.0
        vy = _num(kick.details.get('ball_vy'), 0.0) or 0.0
        direction = attack_direction(kick.cycle, side)
        speed = math.hypot(vx, vy)
        toward_goal = vx * direction > 0.6
        if not toward_goal or speed < SHOT_MIN_SPEED:
            continue

        window_end = min(kick.cycle + PASS_WINDOW, max(b_by_cycle) if b_by_cycle else kick.cycle)
        receiver: PlayerFrame | None = None
        result = 'unknown'
        for cycle in range(kick.cycle + 1, window_end + 1):
            goal_now = any(g.team == kick.team and kick.cycle <= g.cycle <= cycle for g in goal_events)
            if goal_now:
                result = 'goal'
                break
            current_ball = b_by_cycle.get(cycle)
            for player in p_by_cycle.get(cycle, []):
                if current_ball and math.hypot(player.x - current_ball.x, player.y - current_ball.y) <= RECEIVE_DISTANCE:
                    receiver = player
                    if player.team == kick.team and player.unum != kick.unum:
                        result = 'pass_completed'
                    elif player.team != kick.team:
                        result = 'intercepted'
                    break
            if receiver:
                break

        event_type = 'pass' if result == 'pass_completed' else 'shot'
        derived_events.append(MatchEvent(
            match_id,
            kick.cycle,
            event_type,
            kick.team,
            kick.unum,
            kick.x,
            kick.y,
            'high' if result in {'pass_completed', 'goal'} else 'medium',
            {
                'source': 'rcg_inference',
                'outcome': result,
                'receiver_unum': receiver.unum if receiver and receiver.team == kick.team else None,
                'receiver_team': receiver.team if receiver else None,
                'ball_vx': vx,
                'ball_vy': vy,
                'speed': speed,
                'attacking_direction': direction,
                'shot_candidate': True,
                'shot_map_semantics': 'inferred_from_kick_counter_and_ball_velocity',
            },
        ))

    return spatial, derived_events, goal_events


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text('', encoding='utf-8')
        return
    keys = list(rows[0].keys())
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def save_match_data(output_dir: Path, rcg_file: Path, balls: list[BallFrame], players: list[PlayerFrame], spatial: list[dict[str, Any]], events: list[MatchEvent], rcl_file: Path | None = None, actions: list[MatchAction] | None = None) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(rcg_file, output_dir / rcg_file.name)
    if rcl_file and rcl_file.exists():
        shutil.copy2(rcl_file, output_dir / rcl_file.name)
    _write_csv(output_dir / 'ball.csv', [asdict(x) for x in balls])
    _write_csv(output_dir / 'players.csv', [asdict(x) for x in players])
    _write_csv(output_dir / 'spatial.csv', spatial)
    event_rows = [asdict(x) | {'details': json.dumps(x.details, ensure_ascii=False, sort_keys=True)} for x in events]
    _write_csv(output_dir / 'events.csv', event_rows)
    _write_csv(output_dir / 'passes.csv', [row for row in event_rows if row['event_type'] == 'pass'])
    _write_csv(output_dir / 'shots.csv', [row for row in event_rows if row['event_type'] == 'shot'])
    _write_csv(output_dir / 'goals.csv', [row for row in event_rows if row['event_type'] == 'goal'])
    action_rows = [asdict(x) for x in (actions or [])]
    _write_csv(output_dir / 'actions.csv', action_rows)

    summary = {
        'cycles': len(balls),
        'ball_frames': len(balls),
        'player_frames': len(players),
        'events': len(events),
        'goals': sum(1 for event in events if event.event_type == 'goal'),
        'passes': sum(1 for event in events if event.event_type == 'pass'),
        'shots': sum(1 for event in events if event.event_type == 'shot'),
        'spatial_frames': len(spatial),
        'data_sources': ['rcg'] + (['rcl'] if rcl_file and rcl_file.exists() else []),
        'derived_metrics': ['possession', 'pressure', 'territory', 'space_control'],
        'event_inference': 'kick-count based for pass/shot candidates; score/playmode for goals',
        'actions': len(actions or []),
        'action_types': sorted({a.action_type for a in (actions or [])}),
    }
    (output_dir / 'summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return summary
