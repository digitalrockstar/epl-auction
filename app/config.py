import os

CAPTAIN_BASE_PRICE = int(os.getenv("CAPTAIN_BASE_PRICE", 300000))
PLAYER_BASE_PRICE = int(os.getenv("PLAYER_BASE_PRICE", 50000))
MIN_SQUAD_SIZE = int(os.getenv("MIN_SQUAD_SIZE", 12))
MAX_PURSE = int(os.getenv("MAX_PURSE", 2500000))
TIMER_SECONDS = int(os.getenv("TIMER_SECONDS", 90))
REVEAL_SECONDS = int(os.getenv("REVEAL_SECONDS", 12))
RESULT_HOLD_SECONDS = int(os.getenv("RESULT_HOLD_SECONDS", 7))
TICKER_SPEED_SECONDS = int(os.getenv("TICKER_SPEED_SECONDS", 36))
TICKER_WINDOW = int(os.getenv("TICKER_WINDOW", 15))

SKILL_CATEGORIES = ["Batting", "Bowling", "All-Rounder [Batting]", "All-Rounder [Bowling]"]

# (ceiling, increment) - applies while current_bid < ceiling
INCREMENT_SLABS = [
    (100000, 5000),
    (200000, 10000),
    (300000, 20000),
    (400000, 25000),
    (float("inf"), 50000),
]

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

MATCH_OVERS = 20
GROUNDS = ["Legends Ground B", "Legends Ground C", "AXI Cricket Ground"]
