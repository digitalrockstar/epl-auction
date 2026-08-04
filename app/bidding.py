from app.config import INCREMENT_SLABS, CAPTAIN_BASE_PRICE, PLAYER_BASE_PRICE, MIN_SQUAD_SIZE
from app.models import AuctionType


def base_price_for(auction_type) -> int:
    return CAPTAIN_BASE_PRICE if auction_type == AuctionType.captain else PLAYER_BASE_PRICE


def increment_for(current_bid: int, slabs=None) -> int:
    slabs = slabs or INCREMENT_SLABS
    for ceiling, step in slabs:
        if current_bid < ceiling:
            return step
    return slabs[-1][1]


def next_bid_amount(auction, slabs=None) -> int:
    """The exact amount the next bid must be, given slab-based increments."""
    if not auction.current_team_id:
        return auction.base_price
    return auction.current_bid + increment_for(auction.current_bid, slabs)


def purse_check(team, auction_type, bid_amount: int, players_bought: int) -> str:
    """Returns an error string if the bid would break the purse rule, else None.
    Rule: after buying this player, team must still be able to afford the
    minimum remaining squad at base price."""
    if players_bought >= MIN_SQUAD_SIZE:
        return f"{team.name} already has a full squad of {MIN_SQUAD_SIZE}, cannot bid further"

    if auction_type == AuctionType.captain and team.captain_id:
        return f"{team.name} already has a captain, cannot bid for another"

    if bid_amount > team.purse_remaining:
        return f"{team.name} only has {team.purse_remaining} left in purse"

    remaining_needed = MIN_SQUAD_SIZE - (players_bought + 1)
    if remaining_needed > 0:
        reserve = remaining_needed * PLAYER_BASE_PRICE
        if (team.purse_remaining - bid_amount) < reserve:
            return (
                f"{team.name} must keep {reserve} in reserve for "
                f"{remaining_needed} more players, this bid leaves too little"
            )
    return None
