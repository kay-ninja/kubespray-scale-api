#!/bin/bash
# Helper script to view Kubespray API logs

API_URL="${API_URL:-http://localhost:5000}"
LINES="${1:-100}"

if [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
  cat << EOF
Usage: $0 [lines] [options]

View Kubespray API logs

Arguments:
  lines       Number of log lines to retrieve (default: 100)

Options:
  -h, --help  Show this help message
  -f          Follow logs (tail -f style)
  -e          Show only ERROR level logs
  -w          Show only WARNING and ERROR logs

Examples:
  $0              # Show last 100 lines
  $0 500          # Show last 500 lines
  $0 -f           # Follow logs in real-time
  $0 -e           # Show only errors
  $0 1000 -e      # Show last 1000 lines, filter for errors

Environment:
  API_URL         API endpoint (default: http://localhost:5000)
EOF
  exit 0
fi

# Check if following logs
if [ "$1" = "-f" ] || [ "$2" = "-f" ]; then
  echo "Following logs... (Ctrl+C to stop)"
  while true; do
    clear
    curl -s "$API_URL/logs?lines=50" | jq -r '.logs' 2>/dev/null || {
      echo "Failed to fetch logs from API"
      echo "Make sure API is running at: $API_URL"
      exit 1
    }
    sleep 2
  done
  exit 0
fi

# Fetch logs
RESPONSE=$(curl -s "$API_URL/logs?lines=$LINES")

if [ $? -ne 0 ]; then
  echo "Error: Failed to connect to API at $API_URL"
  exit 1
fi

# Parse response
LOGS=$(echo "$RESPONSE" | jq -r '.logs' 2>/dev/null)
TOTAL=$(echo "$RESPONSE" | jq -r '.total_lines' 2>/dev/null)
RETURNED=$(echo "$RESPONSE" | jq -r '.returned_lines' 2>/dev/null)

if [ "$LOGS" = "null" ] || [ -z "$LOGS" ]; then
  echo "Error: No logs returned"
  echo "$RESPONSE" | jq '.' 2>/dev/null || echo "$RESPONSE"
  exit 1
fi

# Display header
echo "=== Kubespray API Logs ==="
echo "Total lines in log file: $TOTAL"
echo "Showing last: $RETURNED lines"
echo "=============================="
echo

# Filter if requested
if [ "$1" = "-e" ] || [ "$2" = "-e" ]; then
  echo "$LOGS" | grep " ERROR "
elif [ "$1" = "-w" ] || [ "$2" = "-w" ]; then
  echo "$LOGS" | grep -E " (ERROR|WARNING) "
else
  echo "$LOGS"
fi
