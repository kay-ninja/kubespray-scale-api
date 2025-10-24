# Kubespray API Logging Guide

## Overview

The Kubespray Scale API now includes comprehensive logging with:
- **Rotating file logs** - Automatic log rotation when files reach 10MB
- **5 backup files** - Keeps up to 5 old log files (50MB total)
- **Dual output** - Logs to both file and console
- **API endpoint** - Retrieve logs via REST API

## Log Location

**Main log file:**
```
/var/log/kubespray-api/kubespray-api.log
```

**Rotated logs:**
```
/var/log/kubespray-api/kubespray-api.log.1
/var/log/kubespray-api/kubespray-api.log.2
/var/log/kubespray-api/kubespray-api.log.3
/var/log/kubespray-api/kubespray-api.log.4
/var/log/kubespray-api/kubespray-api.log.5
```

## Log Rotation Settings

- **Max file size:** 10MB per file
- **Backup count:** 5 files
- **Total storage:** ~50MB maximum
- **Rotation:** Automatic when file reaches size limit

## Viewing Logs

### Method 1: Direct File Access (on bastion)

```bash
# View recent logs
tail -f /var/log/kubespray-api/kubespray-api.log

# View last 100 lines
tail -n 100 /var/log/kubespray-api/kubespray-api.log

# Search for errors
grep ERROR /var/log/kubespray-api/kubespray-api.log

# View all rotated logs
cat /var/log/kubespray-api/kubespray-api.log*
```

### Method 2: API Endpoint (from anywhere)

**Get last 100 lines:**
```bash
curl "http://91.99.14.172:5000/logs"
```

**Get last 500 lines:**
```bash
curl "http://91.99.14.172:5000/logs?lines=500"
```

**Pretty format:**
```bash
curl -s "http://91.99.14.172:5000/logs?lines=200" | jq -r '.logs'
```

**Get full response with metadata:**
```bash
curl -s "http://91.99.14.172:5000/logs" | jq
```

Response format:
```json
{
  "log_file": "/var/log/kubespray-api/kubespray-api.log",
  "total_lines": 1234,
  "returned_lines": 100,
  "logs": "2025-10-05 11:00:00 - INFO - Starting...\n..."
}
```

### Method 3: Helper Script

```bash
# View last 100 lines
./view_logs.sh

# View last 500 lines
./view_logs.sh 500

# Follow logs (like tail -f)
./view_logs.sh -f

# Show only errors
./view_logs.sh -e

# Show last 1000 lines, errors only
./view_logs.sh 1000 -e

# Show warnings and errors
./view_logs.sh -w
```

### Method 4: Systemd Journal (legacy)

```bash
# View service logs
journalctl -u kubespray-api

# Follow logs
journalctl -fu kubespray-api

# Recent logs
journalctl -u kubespray-api --since "10 minutes ago"
```

## Log Format

**Detailed format (in file):**
```
2025-10-05 11:34:50,301 - __main__ - INFO - [kubespray_scale_api.py:123] - Message here
```

**Console format:**
```
2025-10-05 11:34:50 - INFO - Message here
```

## What Gets Logged

### INFO Level:
- API startup/shutdown
- Node registration requests
- Inventory updates
- Ansible playbook execution
- Job status changes
- Node verification results

### ERROR Level:
- Failed inventory updates
- Ansible execution errors
- Node verification failures
- API errors

### Example Log Entries:

```
2025-10-05 11:34:50 - INFO - Starting Kubespray Scale API Server...
2025-10-05 11:34:50 - INFO - Kubespray directory: /root/tf-k8s-cluster-1/kubespray
2025-10-05 11:34:50 - INFO - Log file: /var/log/kubespray-api/kubespray-api.log
2025-10-05 11:34:50 - INFO - Log rotation: 10.0MB per file, 5 backups
2025-10-05 11:35:10 - INFO - Successfully updated inventory with worker-4 (10.10.10.24)
2025-10-05 11:35:10 - INFO - Started job worker-4_10.10.10.24 to add node worker-4 (10.10.10.24)
2025-10-05 11:35:10 - INFO - Running command: .venv/bin/ansible-playbook -i inventory scale.yml --limit=worker-4
2025-10-05 11:40:30 - INFO - Successfully added node worker-4
2025-10-05 11:40:30 - ERROR - Failed to add node worker-5: Connection timeout
```

## Debugging Failed Jobs

### Get Ansible Logs from API:

```bash
# Failed jobs automatically include ansible logs
curl -s "http://91.99.14.172:5000/status?hostname=worker-4&ip=10.10.10.24" | jq

# Or force verbose output
curl -s "http://91.99.14.172:5000/status?hostname=worker-4&ip=10.10.10.24&verbose=true" | jq
```

### Check Specific Error:

```bash
# Get logs and filter for a specific job
curl -s "http://91.99.14.172:5000/logs?lines=1000" | jq -r '.logs' | grep "worker-4"

# Or on bastion
grep "worker-4" /var/log/kubespray-api/kubespray-api.log
```

## Log Management

### Manual Log Rotation:

```bash
# Force rotate (if needed)
sudo logrotate -f /etc/logrotate.d/kubespray-api
```

### Clear Old Logs:

```bash
# Remove rotated logs
sudo rm /var/log/kubespray-api/kubespray-api.log.[1-5]

# Truncate current log
sudo truncate -s 0 /var/log/kubespray-api/kubespray-api.log

# Restart API to start fresh
sudo systemctl restart kubespray-api
```

### Monitor Log Size:

```bash
# Check log sizes
du -sh /var/log/kubespray-api/*

# Watch log growth
watch -n 5 'ls -lh /var/log/kubespray-api/'
```

## Integration Examples

### Monitor for Failures:

```bash
#!/bin/bash
# Alert on errors
while true; do
  ERRORS=$(curl -s "http://91.99.14.172:5000/logs?lines=100" | jq -r '.logs' | grep -c ERROR || echo 0)
  if [ $ERRORS -gt 0 ]; then
    echo "WARNING: $ERRORS errors in last 100 log lines!"
    # Send alert
  fi
  sleep 60
done
```

### Export Logs:

```bash
# Download logs via API
curl -s "http://91.99.14.172:5000/logs?lines=10000" | jq -r '.logs' > kubespray-api-export.log

# Or copy from server
scp root@91.99.14.172:/var/log/kubespray-api/kubespray-api.log* ./logs/
```

### Search Across All Logs:

```bash
# Search in all log files (current + rotated)
grep -h "ERROR" /var/log/kubespray-api/kubespray-api.log* | sort -u

# Count errors per day
grep "ERROR" /var/log/kubespray-api/kubespray-api.log* | cut -d' ' -f1 | sort | uniq -c
```

## Troubleshooting

### Logs not appearing:

```bash
# Check log directory permissions
ls -la /var/log/kubespray-api/

# Create if missing
sudo mkdir -p /var/log/kubespray-api
sudo chown root:root /var/log/kubespray-api

# Restart API
sudo systemctl restart kubespray-api
```

### Log file too large:

```bash
# Check rotation settings in code
grep "LOG_MAX_BYTES\|LOG_BACKUP_COUNT" /opt/kubespray-api/kubespray_scale_api.py

# Force immediate rotation
sudo logrotate -f /etc/logrotate.d/kubespray-api
```

### Can't access logs via API:

```bash
# Check API is running
curl http://91.99.14.172:5000/health

# Check log file exists
ls -la /var/log/kubespray-api/kubespray-api.log

# Test endpoint
curl -v "http://91.99.14.172:5000/logs?lines=10"
```

## Best Practices

1. **Regular monitoring** - Check logs daily for errors
2. **Log retention** - Adjust backup count based on needs
3. **Alerting** - Set up monitoring for ERROR level logs
4. **Archiving** - Periodically archive old rotated logs
5. **Analysis** - Review logs after each scaling operation

## API Endpoints Summary

| Endpoint | Description | Example |
|----------|-------------|---------|
| GET /logs | Get recent log entries | `curl "http://api:5000/logs?lines=200"` |
| GET /status?verbose=true | Get job status with ansible logs | `curl "http://api:5000/status?hostname=w4&ip=10.10.10.24&verbose=true"` |
| GET /health | Check API health | `curl "http://api:5000/health"` |
