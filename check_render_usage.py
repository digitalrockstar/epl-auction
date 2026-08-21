import os
import time
import requests
from datetime import datetime as dt
from sqlalchemy import create_engine, text

from render_accounts import load_accounts

DATABASE_URL = os.environ["DATABASE_URL"]
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=280)

for row in load_accounts():
    account, api_key = row["account"], row["api_key"]
    headers = {"accept": "application/json", "authorization": "Bearer " + api_key}

    r = requests.get(
        "https://api.render.com/v1/services?type=web_service&includePreviews=true&limit=20",
        headers=headers,
    )
    svc = r.json()[0]["service"]
    service_id = svc["id"]
    service_url = svc.get("serviceDetails", {}).get("url", "")

    start_time = "2026-08-01T00:00:00Z".replace(":", "%3A")
    end_time = (dt.now().isoformat().split(".")[0] + "Z").replace(":", "%3A")

    time.sleep(2)
    url = f"https://api.render.com/v1/metrics/bandwidth?startTime={start_time}&endTime={end_time}&resource={service_id}"
    r = requests.get(url, headers=headers)
    total_value = sum(entry["value"] for item in r.json() for entry in item.get("values", []))
    usage_gb = total_value / 1024

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO render_bandwidth (account, service_url, usage_gb, updated_at)
                VALUES (:a, :u, :g, now())
                ON CONFLICT (account) DO UPDATE
                SET service_url = :u, usage_gb = :g, updated_at = now()
                """
            ),
            {"a": account, "u": service_url, "g": usage_gb},
        )

    print(f"{account}: {usage_gb:.2f} gb -> {service_url}")
