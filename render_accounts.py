"""
Single source of truth for the 10 Render free-tier accounts.
Reads render_accounts.csv (not committed - see render_accounts.csv.example).
Columns: account,api_key,service_url,theme
"""
import csv
import os

CSV_PATH = os.path.join(os.path.dirname(__file__), "render_accounts.csv")


def load_accounts():
    if not os.path.exists(CSV_PATH):
        raise FileNotFoundError(
            f"{CSV_PATH} not found. Copy render_accounts.csv.example to "
            "render_accounts.csv and fill in real values."
        )
    with open(CSV_PATH, newline="") as f:
        return list(csv.DictReader(f))
