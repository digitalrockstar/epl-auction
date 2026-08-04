from sqlalchemy.orm import Session

from app.models import Player, Team, PlayerTeamImage, Auction, Bid, Match, PlayingXI


def reset_auction_data(db: Session) -> dict:
    """Wipes auction-derived data only. Teams, managers, admins, and all
    player/user rows are left untouched except for the specific fields that
    are a *result* of the auction (team_id, sold_price, is_captain on Player;
    captain_id, purse_spent on Team)."""
    counts = {
        "playing_xi": db.query(PlayingXI).delete(synchronize_session=False),
        "bids": db.query(Bid).delete(synchronize_session=False),
        "auctions": db.query(Auction).delete(synchronize_session=False),
        "kit_images": db.query(PlayerTeamImage).delete(synchronize_session=False),
        "matches": db.query(Match).delete(synchronize_session=False),
    }

    teams = db.query(Team).all()
    for t in teams:
        t.captain_id = None
        t.purse_spent = 0

    players = db.query(Player).all()
    for p in players:
        p.team_id = None
        p.sold_price = None
        p.is_captain = False

    db.commit()
    counts["teams_reset"] = len(teams)
    counts["players_reset"] = len(players)
    return counts
