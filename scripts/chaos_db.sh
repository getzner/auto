#!/bin/bash
echo "Chaos testing Postgres..."
echo "Stopping postgres container (trade-db)..."
docker stop trade-db || echo "If the name is different, edit this script."
echo "Waiting 30 seconds for pool timeouts to trigger..."
for i in {1..5}; do
    curl -s http://127.0.0.1:8000/health
    echo ""
    sleep 6
done

echo "Restarting postgres container..."
docker start trade-db
echo "Waiting 15 seconds to check if pool recovers automatically..."
sleep 15
curl -s http://127.0.0.1:8000/health
echo ""
echo "Chaos test complete. You should see 503/error during downtime, and 'ok' afterwards without restarting the API."
