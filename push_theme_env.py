import time
import requests
from sqlalchemy import create_engine, text
import os

from render_accounts import load_accounts

DATABASE_URL = os.environ["DATABASE_URL"]
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=280)

for row in load_accounts():
    account, api_key, theme = row["account"], row["api_key"], row["theme"]
    if not theme:
        continue

    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "authorization": "Bearer " + api_key,
    }

    r = requests.get(
        "https://api.render.com/v1/services?type=web_service&includePreviews=true&limit=20",
        headers=headers,
    )
    service_id = r.json()[0]["service"]["id"]

    url = f"https://api.render.com/v1/services/{service_id}/env-vars/THEME_OVERRIDE"
    resp = requests.put(url, json={"value": theme}, headers=headers)
    ok = resp.status_code in (200, 201)
    status = "OK" if ok else f"FAILED ({resp.status_code})"
    print(f"{account} [{service_id}] THEME_OVERRIDE={theme}: {status}")

    if ok:
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE render_bandwidth SET theme = :t WHERE account = :a"),
                {"t": theme, "a": account},
            )

    time.sleep(1)
