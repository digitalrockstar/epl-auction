from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from app.models import Player, Team, PlayerTeamImage, Auction, AuctionType, AuctionStatus, Bid, Match, PlayingXI


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
        t.timeouts_used = 0

    players = db.query(Player).all()
    for p in players:
        p.team_id = None
        p.sold_price = None
        p.is_captain = False

    db.commit()
    counts["teams_reset"] = len(teams)
    counts["players_reset"] = len(players)
    return counts


def reset_since(db: Session, cutoff_ist: datetime) -> dict:
    """Rolls back everything that happened after `cutoff_ist` (an IST wall-clock
    datetime, same convention as Settings.captain_auction_at), so you can test
    the player's auction and then wipe just that test data while keeping
    whatever was genuinely decided before the cutoff (e.g. the captain's
    auction). Reverses auctions/bids/matches/XI started after the cutoff,
    undoing their effect on team purses and player team assignments.
    """
    cutoff_utc = cutoff_ist - timedelta(hours=5, minutes=30)
    # Timeout usage isn't timestamped per-activation, so there's no way to
    # tell which timeouts were called before vs after the cutoff - reset
    # every team's count, same as a full reset does.
    for t in db.query(Team).all():
        t.timeouts_used = 0
    counts = {"bids": 0, "auctions": 0, "matches": 0, "playing_xi": 0}

    # Auctions (and their bids) rolled/started after the cutoff: undo any
    # purse/team-assignment effect they had, then remove them entirely.
    stale_auctions = db.query(Auction).filter(Auction.started_at > cutoff_utc).all()
    for a in stale_auctions:
        if a.status == AuctionStatus.sold:
            player = a.player
            team = db.query(Team).filter(Team.id == a.current_team_id).first() if a.current_team_id else None
            if team:
                team.purse_spent = max(0, (team.purse_spent or 0) - (a.current_bid or 0))
                if a.auction_type == AuctionType.captain and team.captain_id == player.id:
                    team.captain_id = None
            if player:
                player.team_id = None
                player.sold_price = None
                if a.auction_type == AuctionType.captain:
                    player.is_captain = False
        counts["bids"] += db.query(Bid).filter(Bid.auction_id == a.id).delete(synchronize_session=False)
        db.delete(a)
    counts["auctions"] = len(stale_auctions)

    # Any bids placed after the cutoff on an auction that itself started
    # before the cutoff (edge case): strip them and recompute that
    # auction's current bid/leader from what's left.
    trailing_bid_ids = [
        row[0] for row in db.query(Bid.id).join(Auction, Bid.auction_id == Auction.id)
        .filter(Bid.created_at > cutoff_utc, Auction.started_at <= cutoff_utc).all()
    ]
    affected_auction_ids = {
        row[0] for row in db.query(Bid.auction_id).filter(Bid.id.in_(trailing_bid_ids)).all()
    } if trailing_bid_ids else set()
    if trailing_bid_ids:
        counts["bids"] += db.query(Bid).filter(Bid.id.in_(trailing_bid_ids)).delete(synchronize_session=False)
    for auction_id in affected_auction_ids:
        auction = db.query(Auction).filter(Auction.id == auction_id).first()
        if not auction:
            continue
        last = db.query(Bid).filter(Bid.auction_id == auction.id).order_by(Bid.created_at.desc()).first()
        auction.current_bid = last.amount if last else auction.base_price
        auction.current_team_id = last.team_id if last else None

    counts["playing_xi"] = db.query(PlayingXI).filter(PlayingXI.created_at > cutoff_utc).delete(synchronize_session=False)
    counts["matches"] = db.query(Match).filter(Match.created_at > cutoff_utc).delete(synchronize_session=False)

    db.commit()
    return counts
