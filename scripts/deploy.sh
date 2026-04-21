#!/bin/bash
set -e

echo "[deploy] Starting deployment..."

cd "$(dirname "$0")/.."

echo "[deploy] Pulling latest code..."
git pull origin main

echo "[deploy] Installing dependencies..."
pip install -r requirements.txt

echo "[deploy] Restarting service..."
if command -v systemctl &> /dev/null && [ -f /etc/systemd/system/auto-garment-web.service ]; then
    sudo systemctl restart auto-garment-web
elif command -v launchctl &> /dev/null && [ -f "$HOME/Library/LaunchAgents/auto-garment-web.plist" ]; then
    launchctl kickstart -k "gui/$(id -u)/auto-garment-web" || \
    (launchctl unload "$HOME/Library/LaunchAgents/auto-garment-web.plist" 2>/dev/null; \
     launchctl load "$HOME/Library/LaunchAgents/auto-garment-web.plist")
elif command -v pm2 &> /dev/null; then
    pm2 restart auto-garment-web || pm2 start "uvicorn app.main:app --host 0.0.0.0 --port 3000" --name auto-garment-web
else
    pkill -f "uvicorn app.main:app" || true
    sleep 1
    nohup uvicorn app.main:app --host 0.0.0.0 --port 3000 > uvicorn.log 2>&1 &
fi

echo "[deploy] Deployment complete."
