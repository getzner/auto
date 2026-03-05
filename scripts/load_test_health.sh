#!/bin/bash
echo "Running load test on /health endpoint..."
# We will run 100 concurrent requests, 500 total
ab -n 500 -c 100 http://127.0.0.1:8000/health
if [ $? -eq 0 ]; then
    echo "Load test completed successfully. Check for 503 vs 200, but no hangs!"
else
    echo "Load test failed to execute. Ensure 'ab' (apache bench) is installed."
fi
