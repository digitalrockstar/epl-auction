import enum
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey, Enum, Text, Float, UniqueConstraint
)
from sqlalchemy.orm import relationship
from app.database import Base


class Role(str, enum.Enum):
    super_admin = "super_admin"
    admin = "admin"
    manager = "manager"
    captain = "captain"
    player = "player"


class AuctionType(str, enum.Enum):
    captain = "captain"
    player = "player"


class AuctionStatus(str, enum.Enum):
    pending = "pending"
    live = "live"
    sold = "sold"
    unsold = "unsold"
    closed = "closed"


class PaymentStatus(str, enum.Enum):
    pending = "pending"
    paid = "paid"


class User(Base):
    """Every human in the system logs in as a User. Role decides what they can do."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    phone = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(Enum(Role), nullable=False, default=Role.player)
    created_at = Column(DateTime, default=datetime.utcnow)

    player_profile = relationship("Player", back_populates="user", uselist=False)
    managed_team = relationship("Team", back_populates="manager", uselist=False)


class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    manager_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    captain_id = Column(Integer, ForeignKey("players.id"), nullable=True)
    purse_total = Column(Integer, default=0)   # total budget for player auction
    purse_spent = Column(Integer, default=0)
    timeouts_used = Column(Integer, default=0)
    logo_url = Column(String, nullable=True)
    primary_color = Column(String, nullable=True)
    secondary_color = Column(String, nullable=True)

    manager = relationship("User", back_populates="managed_team", foreign_keys=[manager_id])
    captain = relationship("Player", foreign_keys=[captain_id], post_update=True)
    players = relationship("Player", back_populates="team", foreign_keys="Player.team_id")

    @property
    def purse_remaining(self):
        return self.purse_total - self.purse_spent


class Player(Base):
    """A registered player. wants_captaincy flags if they go into the captain's pool."""
    __tablename__ = "players"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=True)
    wants_captaincy = Column(Boolean, default=False)
    fee_status = Column(Enum(PaymentStatus), default=PaymentStatus.pending)
    fee_amount = Column(Integer, default=1700)
    sold_price = Column(Integer, nullable=True)
    is_captain = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # registration (forms.app)
    primary_skill = Column(String, nullable=True)
    batting_position = Column(String, nullable=True)
    batting_hand = Column(String, nullable=True)
    bowling_style = Column(String, nullable=True)
    bowling_hand = Column(String, nullable=True)
    is_wicketkeeper = Column(String, nullable=True)
    experience_level = Column(String, nullable=True)
    brief = Column(Text, nullable=True)
    profile_photo_url = Column(String, nullable=True)
    cricheroes_url = Column(String, nullable=True)

    # CricHeroes stats
    matches_won = Column(Integer, nullable=True)
    matches_lost = Column(Integer, nullable=True)

    bat_matches = Column(Integer, nullable=True)
    bat_innings = Column(Integer, nullable=True)
    bat_runs = Column(Integer, nullable=True)
    bat_sr = Column(Float, nullable=True)
    bat_avg = Column(Float, nullable=True)
    bat_4s = Column(Integer, nullable=True)
    bat_6s = Column(Integer, nullable=True)
    bat_30s = Column(Integer, nullable=True)
    bat_ducks = Column(Integer, nullable=True)

    bowl_matches = Column(Integer, nullable=True)
    bowl_innings = Column(Integer, nullable=True)
    bowl_wickets = Column(Integer, nullable=True)
    bowl_economy = Column(Float, nullable=True)
    bowl_3wkts = Column(Integer, nullable=True)
    bowl_dots = Column(Integer, nullable=True)
    bowl_extras = Column(Integer, nullable=True)
    bowl_4s_given = Column(Integer, nullable=True)
    bowl_6s_given = Column(Integer, nullable=True)

    field_catches = Column(Integer, nullable=True)
    field_runouts = Column(Integer, nullable=True)

    user = relationship("User", back_populates="player_profile")
    team = relationship("Team", back_populates="players", foreign_keys=[team_id])
    kit_images = relationship("PlayerTeamImage", back_populates="player")


class PlayerTeamImage(Base):
    __tablename__ = "player_team_images"
    __table_args__ = (UniqueConstraint("player_id", "team_id", name="uq_player_team_image"),)

    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    image_url = Column(String, nullable=False)

    player = relationship("Player", back_populates="kit_images")
    team = relationship("Team")


class Auction(Base):
    """One row per player/captain that goes under the hammer."""
    __tablename__ = "auctions"

    id = Column(Integer, primary_key=True)
    auction_type = Column(Enum(AuctionType), nullable=False)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    status = Column(Enum(AuctionStatus), default=AuctionStatus.pending)
    base_price = Column(Integer, default=0)
    current_bid = Column(Integer, default=0)
    current_team_id = Column(Integer, ForeignKey("teams.id"), nullable=True)
    started_at = Column(DateTime, nullable=True)
    last_action_at = Column(DateTime, nullable=True)
    closed_at = Column(DateTime, nullable=True)
    # Play/pause: while set, this is the frozen seconds-left and the main
    # timer does not count down or auto-expire.
    paused_remaining_seconds = Column(Integer, nullable=True)
    # Team timeout: an alternate countdown that also freezes the main timer
    # for its duration, auto-resuming (or admin can end it early) once done.
    timeout_team_id = Column(Integer, ForeignKey("teams.id"), nullable=True)
    timeout_started_at = Column(DateTime, nullable=True)

    player = relationship("Player")
    current_team = relationship("Team", foreign_keys=[current_team_id])
    bids = relationship("Bid", back_populates="auction")


class Bid(Base):
    """Every bid entered by the admin during an auction. Full history, nothing overwritten."""
    __tablename__ = "bids"

    id = Column(Integer, primary_key=True)
    auction_id = Column(Integer, ForeignKey("auctions.id"), nullable=False)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    amount = Column(Integer, nullable=False)
    entered_by_admin_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    auction = relationship("Auction", back_populates="bids")
    team = relationship("Team")
    entered_by = relationship("User")


class Match(Base):
    __tablename__ = "matches"

    id = Column(Integer, primary_key=True)
    match_number = Column(Integer, nullable=False)
    match_type = Column(String, default="league")  # league / qualifier / final
    team_a_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    team_b_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    match_date = Column(DateTime, nullable=False)
    ground_fee = Column(Integer, default=8500)
    winner_team_id = Column(Integer, ForeignKey("teams.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    team_a = relationship("Team", foreign_keys=[team_a_id])
    team_b = relationship("Team", foreign_keys=[team_b_id])
    winner = relationship("Team", foreign_keys=[winner_team_id])


class PlayingXI(Base):
    """Links a player to a match they played. Lets us auto-check the min-2-games rule."""
    __tablename__ = "playing_xi"

    id = Column(Integer, primary_key=True)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=False)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    match = relationship("Match")
    player = relationship("Player")


class Settings(Base):
    """Single-row table (id always 1) holding admin-tunable knobs that would
    otherwise require an env var change and redeploy."""
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True)
    telegram_enabled = Column(Boolean, default=True)
    timer_seconds = Column(Integer, default=90)
    ticker_speed_seconds = Column(Integer, default=36)
    ticker_window = Column(Integer, default=15)
    increment_slabs = Column(Text, nullable=True)  # JSON: [[ceiling_or_null, increment], ...]
    timeout_seconds = Column(Integer, default=30)
    max_timeouts_per_team = Column(Integer, default=1)
    light_theme = Column(Boolean, default=False)  # legacy, kept for old rows; theme below is authoritative
    theme = Column(String, default="dark")  # dark, light, epl-night, graphite-gold, warm-ivory, clean-broadcast
    captain_auction_at = Column(DateTime, default=datetime(2026, 8, 7, 21, 0))  # IST wall-clock, no tz stored
    player_auction_at = Column(DateTime, default=datetime(2026, 8, 22, 17, 0))
