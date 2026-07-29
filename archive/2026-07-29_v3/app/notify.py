import requests
from app.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID


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
