from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ResultRules:
    tournament_type: str
    draws_allowed: bool
    draw_advances_team2: bool
    penalties_enabled: bool

    def resolve_winner(
        self,
        team1: str,
        score1: int,
        team2: str,
        score2: int,
        penalty1: int | None = None,
        penalty2: int | None = None,
    ) -> str:
        if score1 > score2:
            return team1
        if score2 > score1:
            return team2

        if penalty1 is not None and penalty2 is not None:
            if penalty1 == penalty2:
                raise ValueError("Penalty scores cannot be equal when resolving a winner")
            return team1 if penalty1 > penalty2 else team2

        if self.draw_advances_team2:
            return team2
        if self.draws_allowed:
            return "Draw (no penalties)"
        raise ValueError("Match is drawn but the configured rules require a winner")


def rules_for(tournament_type: str, penalties_enabled: bool) -> ResultRules:
    if tournament_type == "stepladder":
        return ResultRules(
            tournament_type=tournament_type,
            draws_allowed=False,
            draw_advances_team2=True,
            penalties_enabled=penalties_enabled,
        )
    return ResultRules(
        tournament_type=tournament_type,
        draws_allowed=True,
        draw_advances_team2=False,
        penalties_enabled=penalties_enabled,
    )
