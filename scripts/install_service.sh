#!/usr/bin/env bash
# install_service.sh — Install trade-api as a systemd service
# Run once on the VPS: bash scripts/install_service.sh

set -e
echo "=== Installing trade-api systemd service ==="

# Copy service file
cp /opt/trade_server/scripts/trade-api.service /etc/systemd/system/trade-api.service

# Reload daemon and enable
systemctl daemon-reload
systemctl enable trade-api
systemctl restart trade-api

echo ""
echo "=== Done! Useful commands ==="
echo "  Status:    systemctl status trade-api"
echo "  Logs:      journalctl -u trade-api -f"
echo "  Restart:   systemctl restart trade-api"
echo "  Stop:      systemctl stop trade-api"
echo "  Dashboard: http://$(curl -s ifconfig.me):8000/dashboard"
