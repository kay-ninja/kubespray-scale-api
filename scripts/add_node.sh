#!/bin/bash
# Example script to add a node and monitor its progress

set -e

API_URL="${API_URL:-http://localhost:5000}"
HOSTNAME="${1:-worker-4}"
IP="${2:-10.10.10.24}"

echo "Adding node $HOSTNAME ($IP) to the cluster..."

# Add the node
RESPONSE=$(curl -s -X POST "$API_URL/add-node" \
  -H "Content-Type: application/json" \
  -d "{\"hostname\": \"$HOSTNAME\", \"ip\": \"$IP\"}")

echo "Response: $RESPONSE"
echo ""

# Extract status
STATUS=$(echo "$RESPONSE" | jq -r '.status')

if [ "$STATUS" != "okay" ]; then
  echo "Failed to start job!"
  exit 1
fi

echo "Job started successfully. Monitoring progress..."
echo ""

# Poll for status
while true; do
  SLEEP_TIME=10
  STATUS_RESPONSE=$(curl -s "$API_URL/status?hostname=$HOSTNAME&ip=$IP")
  JOB_STATUS=$(echo "$STATUS_RESPONSE" | jq -r '.status')
  MESSAGE=$(echo "$STATUS_RESPONSE" | jq -r '.message')
  
  TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
  echo "[$TIMESTAMP] Status: $JOB_STATUS - $MESSAGE"
  
  if [ "$JOB_STATUS" = "completed" ]; then
    echo ""
    echo "✓ Node successfully added!"
    echo ""
    echo "Full status:"
    echo "$STATUS_RESPONSE" | jq .
    
    # Show node info
    NODE_READY=$(echo "$STATUS_RESPONSE" | jq -r '.node_status.ready')
    if [ "$NODE_READY" = "true" ]; then
      echo ""
      echo "✓ Node is READY in the cluster"
    fi
    
    exit 0
  elif [ "$JOB_STATUS" = "failed" ]; then
    echo ""
    echo "✗ Job failed!"
    echo ""
    echo "Full status:"
    echo "$STATUS_RESPONSE" | jq .
    exit 1
  elif [ "$JOB_STATUS" = "running" ]; then
    SLEEP_TIME=15
  fi
  
  sleep $SLEEP_TIME
done
