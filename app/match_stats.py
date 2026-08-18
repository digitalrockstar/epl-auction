"""Cricket scoring helpers: overs<->balls conversion and Net Run Rate."""
from app.config import MATCH_OVERS


def overs_to_balls(overs: float) -> int:
    """Convert cricket overs notation (e.g. 19.3 = 19 overs, 3 balls) to total balls."""
    whole = int(overs)
    balls_part = round((overs - whole) * 10)
    balls_part = min(balls_part, 5)  # guard bad input like 19.7
    return whole * 6 + balls_part


def balls_to_decimal_overs(balls: int) -> float:
    """True decimal overs (balls / 6) for NRR math, distinct from cricket notation."""
    return balls / 6


def effective_balls(overs: float, wickets: int) -> int:
    """All-out before quota => full quota overs count for NRR, not overs actually faced."""
    if wickets is not None and wickets >= 10:
        return MATCH_OVERS * 6
    return overs_to_balls(overs)


def determine_winner(match):
    """Returns (winner_team_id, is_tie). None winner + is_tie False means result not entered."""
    if match.team_a_runs is None or match.team_b_runs is None:
        return None, False
    if match.team_a_runs > match.team_b_runs:
        return match.team_a_id, False
    if match.team_b_runs > match.team_a_runs:
        return match.team_b_id, False
    return None, True


def has_result(match) -> bool:
    return match.team_a_runs is not None and match.team_b_runs is not None
