#!/bin/bash
# Helper script to remove a node from the Kubespray cluster

set -e

# Configuration
API_URL="${API_URL:-http://localhost:5000}"
HOSTNAME="${1}"
IP="${2}"
SKIP_K8S="${3:-false}"

if [ "$1" = "-h" ] || [ "$1" = "--help" ] || [ -z "$HOSTNAME" ]; then
  cat << EOF
Usage: $0 <hostname> [ip] [skip_k8s]

Remove a node from the Kubernetes cluster and inventory

Arguments:
  hostname    Node hostname to remove (required)
  ip          Node IP address (optional, for tracking)
  skip_k8s    Skip Kubernetes removal (true/false, default: false)

Examples:
  $0 apps-hie4aema                    # Remove node (drain + delete from k8s + inventory)
  $0 apps-hie4aema 10.10.10.2         # Same, with IP for tracking
  $0 apps-hie4aema 10.10.10.2 true   # Only remove from inventory, skip k8s

Environment:
  API_URL     API endpoint (default: http://localhost:5000)

Notes:
  - Master nodes cannot be removed (safety check)
  - Inventory is automatically backed up before removal
  - Node will be drained before deletion from Kubernetes
  - Use skip_k8s=true if node is already gone from cluster
EOF
  exit 0
fi

# Build query parameters
QUERY="hostname=$HOSTNAME"
[ -n "$IP" ] && QUERY="$QUERY&ip=$IP"
[ "$SKIP_K8S" = "true" ] && QUERY="$QUERY&skip_k8s=true"

echo "Removing node: $HOSTNAME"
[ -n "$IP" ] && echo "IP: $IP"
[ "$SKIP_K8S" = "true" ] && echo "Skipping Kubernetes removal"
echo ""
echo "This will:"
if [ "$SKIP_K8S" != "true" ]; then
  echo "  1. Drain the node from Kubernetes"
  echo "  2. Delete the node from Kubernetes"
  echo "  3. Remove from inventory"
else
  echo "  1. Remove from inventory only"
fi
echo ""

read -p "Are you sure you want to continue? [y/N] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
  echo "Cancelled"
  exit 0
fi

echo ""
echo "Removing node..."

# Make the API call
RESPONSE=$(curl -s -w "\n%{http_code}" -X DELETE "$API_URL/remove-node?$QUERY")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" = "200" ]; then
  echo "Success! Node removed."
  echo ""
  echo "$BODY" | python3 -m json.tool 2>/dev/null || echo "$BODY"
  
  # Show results
  echo ""
  echo "=== Removal Summary ==="
  
  if [ "$SKIP_K8S" != "true" ]; then
    K8S_DELETED=$(echo "$BODY" | python3 -c "import sys, json; print(json.load(sys.stdin).get('result', {}).get('kubernetes', {}).get('deleted', False))" 2>/dev/null)
    K8S_DRAINED=$(echo "$BODY" | python3 -c "import sys, json; print(json.load(sys.stdin).get('result', {}).get('kubernetes', {}).get('drained', False))" 2>/dev/null)
    
    if [ "$K8S_DRAINED" = "True" ]; then
      echo "  Kubernetes drain: SUCCESS"
    else
      echo "  Kubernetes drain: FAILED (check logs)"
    fi
    
    if [ "$K8S_DELETED" = "True" ]; then
      echo "  Kubernetes delete: SUCCESS"
    else
      echo "  Kubernetes delete: FAILED (check logs)"
    fi
  fi
  
  INVENTORY_REMOVED=$(echo "$BODY" | python3 -c "import sys, json; print(json.load(sys.stdin).get('result', {}).get('inventory', False))" 2>/dev/null)
  if [ "$INVENTORY_REMOVED" = "True" ]; then
    echo "  Inventory removal: SUCCESS"
  else
    echo "  Inventory removal: FAILED"
  fi
  
  echo ""
  echo "Node $HOSTNAME has been removed."
  
  # Verify
  echo ""
  echo "Verify removal:"
  echo "  kubectl get nodes | grep $HOSTNAME"
  echo "  cat ~/tf-k8s-cluster-1/kubespray/inventory/mycluster/hosts.yaml | grep $HOSTNAME"
  
  exit 0
else
  echo "Error: Failed to remove node (HTTP $HTTP_CODE)"
  echo ""
  echo "$BODY" | python3 -m json.tool 2>/dev/null || echo "$BODY"
  exit 1
fi
