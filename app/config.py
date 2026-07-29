import os

CAPTAIN_BASE_PRICE = int(os.getenv("CAPTAIN_BASE_PRICE", 200000))
PLAYER_BASE_PRICE = int(os.getenv("PLAYER_BASE_PRICE", 50000))
MIN_SQUAD_SIZE = int(os.getenv("MIN_SQUAD_SIZE", 13))
MAX_PURSE = int(os.getenv("MAX_PURSE", 2500000))
TIMER_SECONDS = int(os.getenv("TIMER_SECONDS", 180))

# (ceiling, increment) - applies while current_bid < ceiling
INCREMENT_SLABS = [
    (100000, 10000),
    (200000, 20000),
    (400000, 40000),
    (float("inf"), 50000),
]

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
