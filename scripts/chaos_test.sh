#!/bin/bash
# Herstelplan: Chaos Engineering Test
# Dit script simuleert failures om de robuustheid (self-healing) te testen.
# WAARSCHUWING: Run dit niet in productie tenzij gepland!

echo "🚀 Starting Chaos Test for Trade Server..."
echo "WARNING: Dit zal containers doden en/of systemen verstoren."
read -p "Weet je zeker dat je wilt doorgaan? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]
then
    echo "Chaos test geannuleerd."
    exit 1
fi

echo "Stap 1: Testen van Database Failure (Postgres OOM / Kill)..."
echo "Killing trade_postgres..."
docker kill trade_postgres
echo "Postgres is now offline. Wachten voor 5 seconden..."
sleep 5
echo "Check de api of main logs om retries / verbindingfouten te observeren."
sleep 10
echo "Stap 1 Herstel: Postgres wordt herstart door Docker ('restart: unless-stopped') of manueel:"
docker start trade_postgres
echo "Wacht op database healthcheck..."
sleep 10
echo "Postgres hersteld."

echo ""
echo "Stap 2: Testen van Redis Cache Eviction of Downtime..."
echo "Pausing trade_redis..."
docker pause trade_redis
echo "Redis is nu gepauzeerd (frozen). Dit simuleert een hangsituatie."
sleep 10
echo "Stap 2 Herstel: Redis unpausing..."
docker unpause trade_redis
echo "Redis is weer online."

echo ""
echo "Stap 3: Testen API process kill..."
echo "Simuleren van API crash..."
sudo systemctl restart trade-api
echo "Check je uptime monitoring dat het kort gedownd is, maar snel herstelt door systemd."

echo ""
echo "✅ Chaos test cycle compleet."
echo "Controleer de applicatie logs in systemd of journalctl of de applicaties fatsoenlijk zijn hersteld tijdens deze test en er geen corrupte cycles (heartbeats) zijn overgebleven in de db."
