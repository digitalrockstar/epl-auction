import random
import requests
from app.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

TIER1 = ["🎉", "🥳", "🎊", "🙌", "👏"]
TIER2 = ["✨", "🎇", "🎆", "💥", "🌟", "🧨", "💫"]
TIER3 = ["🔥", "🚀", "💰", "🤑"]


def celebration_emojis(amount: int) -> str:
    if amount >= 400000:
        pool = TIER3
    elif amount >= 100000:
        pool = TIER2
    else:
        pool = TIER1
    count = random.randint(2, 4)
    return " ".join(random.choice(pool) for _ in range(count))


def notify(text: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text},
            timeout=3,
        )
    except Exception:
        pass  # never let a notification failure break the auction


def notify_sold(player_name: str, team_name: str, amount: int):
    notify(f"{player_name} sold to {team_name} for ₹{amount:,} {celebration_emojis(amount)}")
