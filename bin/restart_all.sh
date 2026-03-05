#!/bin/bash
# bin/restart_all.sh — Force-restart all trade server components

echo "🚀 Starting full system reset..."

# 1. Stop the service first to break the loop
echo "🛑 Stopping trade-server service..."
systemctl stop trade-server 2>/dev/null

# 2. Kill any existing python processes (server and main)
echo "🛑 Killing all Python processes..."
pkill -9 -f python 2>/dev/null
# Force kill port 8000 just in case
fuser -k 8000/tcp 2>/dev/null

# 2. Fix permissions (in case rsync was run as root)
echo "🔧 Fixing file permissions..."
chown -R trader:trader /opt/trade_server
chown -R trader:trader /opt/trade_env
chmod +x /opt/trade_server/bin/*.sh 2>/dev/null

# 3. Ensure Docker containers are healthy
echo "🐳 Ensuring Docker containers (DB/Redis/Ollama) are running..."
docker compose -f /opt/trade_server/docker-compose.yml up -d

# 4. Restart the API and Main services
echo "🖥️ Restarting trade-server and trade-main..."
systemctl restart trade-server trade-main

# 5. Wait for API to become healthy
echo "⏳ Waiting for startup..."
for i in {1..10}; do
    if curl -s http://localhost:8000/health | grep -q "healthy"; then
        echo "✅ API is HEALTHY"
        break
    fi
    sleep 2
done

# If it didn't break out with success, do a final check
if ! curl -s http://localhost:8000/health | grep -q "healthy"; then
    echo "❌ API is DEGRADED (check journalctl -u trade-server)"
fi

echo "------------------------------------------------"
echo "Done! The API and background services are running."
echo "To start the main orchestrator, run:"
echo "  source /opt/trade_env/bin/activate && export PYTHONPATH=\$PYTHONPATH:. && python3 main.py"
echo "------------------------------------------------"
