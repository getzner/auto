#!/bin/bash
# ============================================================
# Agentic Crypto Trading Framework — Server Setup
# Target: Hostinger VPS Ubuntu 24.04 (fresh)
# Run as root: bash setup_server.sh
# ============================================================

set -e
LOG="/var/log/trade_setup.log"
exec > >(tee -a "$LOG") 2>&1

echo "========================================="
echo " Trade Server Setup — $(date)"
echo "========================================="

# ── 1. Baseline packages ──────────────────────────────────
echo "[1/8] Installing baseline packages..."
apt update && apt upgrade -y
apt install -y \
    git curl wget htop ufw fail2ban \
    python3.12 python3.12-venv python3-pip \
    build-essential libssl-dev libffi-dev \
    postgresql-client redis-tools \
    unzip jq

# ── 2. Firewall ───────────────────────────────────────────
echo "[2/8] Configuring UFW firewall..."
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 8000/tcp comment "FastAPI"
ufw allow 3000/tcp comment "Grafana (future)"
ufw --force enable
echo "UFW status:"
ufw status verbose

# ── 3. Fail2ban ───────────────────────────────────────────
echo "[3/8] Enabling fail2ban..."
systemctl enable fail2ban
systemctl start fail2ban

# ── 4. Docker ─────────────────────────────────────────────
echo "[4/8] Installing Docker..."
if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | sh
fi
apt install -y docker-compose-plugin
systemctl enable docker
systemctl start docker

# Create trade user (non-root) if not exists
if ! id "trader" &>/dev/null; then
    useradd -m -s /bin/bash trader
fi
usermod -aG docker trader
echo "Docker version: $(docker --version)"

# ── 5. Ollama ─────────────────────────────────────────────
echo "[5/8] Installing Ollama..."
if ! command -v ollama &>/dev/null; then
    curl -fsSL https://ollama.com/install.sh | sh
fi
systemctl enable ollama
systemctl start ollama
sleep 3

# Pull models (choose based on your RAM)
# 8GB  RAM → use mistral-nemo (7B)
# 16GB RAM → use llama3.2 (8B)  ← recommended
# 32GB RAM → use llama3.1 (70B) for full power
RAM_GB=$(free -g | awk '/^Mem:/{print $2}')
echo "Detected RAM: ${RAM_GB}GB"

# Model selection by available RAM:
#  32GB+ → llama3.1:70b  (best quality)
#  16GB+ → llama3.2      (8B, great balance)
#   8GB+ → llama3.2:3b   (3B, fits comfortably, recommended for this VPS)
#  < 8GB → llama3.2:1b   (1B, minimal)
if [ "$RAM_GB" -ge 30 ]; then
    OLLAMA_MODEL="llama3.1:70b"
elif [ "$RAM_GB" -ge 14 ]; then
    OLLAMA_MODEL="llama3.2"
elif [ "$RAM_GB" -ge 6 ]; then
    OLLAMA_MODEL="llama3.2:3b"
else
    OLLAMA_MODEL="llama3.2:1b"
fi

echo "Pulling Ollama model: $OLLAMA_MODEL"
ollama pull "$OLLAMA_MODEL"
echo "OLLAMA_MODEL=$OLLAMA_MODEL" >> /opt/trade_server/.env 2>/dev/null || true

# ── 6. Python environment ─────────────────────────────────
echo "[6/8] Setting up Python environment..."
python3.12 -m venv /opt/trade_env
/opt/trade_env/bin/pip install --upgrade pip wheel setuptools

# ── 7. Clone project ──────────────────────────────────────
echo "[7/8] Setting up project directory..."
mkdir -p /opt/trade_server
if [ ! -d "/opt/trade_server/.git" ]; then
    # If deploying from local, rsync or git clone here
    echo "INFO: Place your project files in /opt/trade_server"
    echo "      e.g.: rsync -avz ./trade_server/ user@vps:/opt/trade_server/"
fi
chown -R trader:trader /opt/trade_server /opt/trade_env

# ── 8. Systemd services ───────────────────────────────────
echo "[8/8] Creating systemd service for trade server..."
cat > /etc/systemd/system/trade-server.service << 'EOF'
[Unit]
Description=Agentic Crypto Trade Server
After=network.target docker.service ollama.service
Requires=docker.service

[Service]
Type=simple
User=trader
WorkingDirectory=/opt/trade_server
EnvironmentFile=/opt/trade_server/.env
ExecStartPre=/usr/bin/docker compose up -d
ExecStart=/opt/trade_env/bin/python api/server.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
# Don't start yet — needs config first
echo ""
echo "========================================="
echo " Setup complete! Next steps:"
echo "  1. cd /opt/trade_server"
echo "  2. cp .env.example .env && nano .env"
echo "  3. docker compose up -d"
echo "  4. pip install -r requirements.txt"
echo "  5. python data/market_data.py  (test feed)"
echo "  6. systemctl start trade-server"
echo "========================================="
