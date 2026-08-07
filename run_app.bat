@echo off
cd /d D:\Code\EPL\epl-auction
start "" tailscale serve https / http://localhost:8000
uvicorn app.main:app --host 0.0.0.0 --port 8000