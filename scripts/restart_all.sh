#!/bin/bash
# Herstelplan: Full Restart
# Script om alle services geforceerd en in de juiste volgorde te herstarten.
# Gebruik in geval van "Klein Issue" (wanneer heartbeat faalt) of "Service Failure" (als componenten vastlopen).

echo "Initiating full restart sequence..."

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

echo "Stoppen van actieve services via systemd..."
sudo systemctl stop trade-main || echo "trade-main was already stopped or not found."
sudo systemctl stop trade-api || echo "trade-api was already stopped or not found."
sudo systemctl stop trade-monitor || echo "trade-monitor was already stopped or not found."

echo "Docker containers herstarten..."
# We stoppen eerst alle containers zachtjes, en verwijderen ze dan
docker compose down

echo "Wachten op poorten om vrij te komen..."
sleep 2

echo "Opstarten van Docker containers (Postgres, Redis, ChromaDB)..."
docker compose up -d

echo "Wachten tot database en metrics systems healthchecks slagen..."
# Sleep to give containers some time to startup usually healthchecks catch this but let's be safe
sleep 10

echo "Opstarten van systemd services..."
sudo systemctl start trade-api
sudo systemctl start trade-main
# sudo systemctl start trade-monitor # Uncomment if trade-monitor is consistently used

echo "Alle services zijn gestart."
echo "Check de status met:"
echo "  sudo systemctl status trade-main"
echo "  docker ps"
echo "  journalctl -u trade-main -f"
