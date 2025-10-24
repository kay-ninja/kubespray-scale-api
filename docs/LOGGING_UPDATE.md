# Logging Update Summary

## What's New

The Kubespray Scale API has been updated with comprehensive logging capabilities:

### ✨ New Features

1. **Rotating File Logs**
   - Logs stored in: `/var/log/kubespray-api/kubespray-api.log`
   - Automatic rotation at 10MB per file
   - Keeps 5 backup files (~50MB total storage)
   - Both file and console output

2. **REST API Log Endpoint**
   - `GET /logs?lines=N` - Retrieve recent log entries
   - Access logs from anywhere without SSH
   - JSON response with metadata

3. **Enhanced Status Endpoint**
   - `GET /status?verbose=true` - Include Ansible logs
   - Failed jobs automatically include full error output
   - Better debugging capabilities

4. **Helper Script**
   - `view_logs.sh` - Easy log viewing tool
   - Follow logs in real-time
   - Filter for errors/warnings
   - Multiple display options

## Updated Files

### 1. **kubespray_scale_api.py** (Updated)
**Changes:**
- Added `RotatingFileHandler` for log management
- New `/logs` endpoint for log retrieval
- Enhanced `/status` endpoint with `verbose` parameter
- Detailed logging throughout the application
- Both file and console logging

**New Configuration:**
```python
LOG_FILE = "/var/log/kubespray-api/kubespray-api.log"
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10MB
LOG_BACKUP_COUNT = 5
```

### 2. **view_logs.sh** (New)
Helper script for viewing logs:
```bash
./view_logs.sh          # Last 100 lines
./view_logs.sh 500      # Last 500 lines
./view_logs.sh -f       # Follow logs
./view_logs.sh -e       # Show only errors
./view_logs.sh -w       # Show warnings/errors
```

### 3. **LOGGING.md** (New)
Complete logging documentation covering:
- Log locations and rotation
- Multiple ways to view logs
- Log format and content
- Debugging techniques
- Best practices

### 4. **README.md** (Updated)
Added sections for:
- New `/logs` endpoint
- Logging overview
- Updated troubleshooting with log commands

## How to Update Your API

### Step 1: Stop Current API
```bash
# On bastion
sudo systemctl stop kubespray-api
```

### Step 2: Update the Script
```bash
cd /opt/kubespray-api
# Replace kubespray_scale_api.py with the new version
```

### Step 3: Create Log Directory
```bash
sudo mkdir -p /var/log/kubespray-api
sudo chown root:root /var/log/kubespray-api
```

### Step 4: Restart API
```bash
sudo systemctl start kubespray-api
```

### Step 5: Verify Logging
```bash
# Check logs are being created
ls -la /var/log/kubespray-api/

# Test log endpoint
curl http://localhost:5000/logs?lines=10

# View startup logs
tail -f /var/log/kubespray-api/kubespray-api.log
```

## New API Endpoint Usage

### Get Recent Logs
```bash
# Default: 100 lines
curl http://91.99.14.172:5000/logs

# Specific number of lines
curl "http://91.99.14.172:5000/logs?lines=500"

# Pretty format
curl -s "http://91.99.14.172:5000/logs" | jq -r '.logs'
```

### Get Job Details with Ansible Logs
```bash
# Verbose status (includes ansible output)
curl "http://91.99.14.172:5000/status?hostname=worker-4&ip=10.10.10.24&verbose=true"

# Extract just the ansible errors
curl -s "http://91.99.14.172:5000/status?hostname=worker-4&ip=10.10.10.24&verbose=true" | \
  jq -r '.ansible_stderr'
```

## Debugging Your Failed Job

Now you can easily debug the failed job from earlier:

### Method 1: Via API with Verbose Flag
```bash
curl -s "http://91.99.14.172:5000/status?hostname=apps-Gie4aema&ip=10.10.10.2&verbose=true" | \
  jq -r '.ansible_stderr'
```

This will show you the exact Ansible error!

### Method 2: Search Logs
```bash
# Using the helper script
./view_logs.sh 1000 -e  # Last 1000 lines, errors only

# Or via API
curl -s "http://91.99.14.172:5000/logs?lines=1000" | \
  jq -r '.logs' | grep -i "apps-Gie4aema"
```

### Method 3: Direct Log Access (on bastion)
```bash
# View all logs related to the job
grep "apps-Gie4aema" /var/log/kubespray-api/kubespray-api.log

# See the ansible command that was run
grep "Running command" /var/log/kubespray-api/kubespray-api.log | tail -1

# View full error context
grep -B 5 -A 10 ERROR /var/log/kubespray-api/kubespray-api.log | tail -20
```

## Log Format Examples

**File log format (detailed):**
```
2025-10-05 11:34:50,301 - __main__ - INFO - [kubespray_scale_api.py:123] - Successfully updated inventory with apps-Gie4aema (10.10.10.2)
2025-10-05 11:34:50,302 - __main__ - INFO - [kubespray_scale_api.py:456] - Running command: .venv/bin/ansible-playbook -i inventory scale.yml --limit=apps-Gie4aema
2025-10-05 11:35:12,328 - __main__ - ERROR - [kubespray_scale_api.py:478] - Failed to add node apps-Gie4aema: Connection timeout
```

**Console format (simple):**
```
2025-10-05 11:34:50 - INFO - Successfully updated inventory
2025-10-05 11:34:50 - INFO - Running ansible playbook
2025-10-05 11:35:12 - ERROR - Failed to add node
```

## Benefits

✅ **Easy Debugging** - Access logs from anywhere via API
✅ **Automatic Rotation** - No manual log management needed
✅ **Full Ansible Output** - Complete error details captured
✅ **Multiple Access Methods** - API, file, helper script
✅ **Searchable** - Grep-friendly format
✅ **Space Efficient** - Only keeps 50MB of logs

## Quick Reference

| Task | Command |
|------|---------|
| View recent logs | `curl http://api:5000/logs` |
| Follow logs | `./view_logs.sh -f` |
| Show only errors | `./view_logs.sh -e` |
| Get job with ansible logs | `curl "http://api:5000/status?hostname=X&ip=Y&verbose=true"` |
| Direct log access | `tail -f /var/log/kubespray-api/kubespray-api.log` |
| Search for errors | `grep ERROR /var/log/kubespray-api/kubespray-api.log` |

## Documentation

- **[LOGGING.md](LOGGING.md)** - Complete logging guide
- **[README.md](README.md)** - Updated API documentation
- **[view_logs.sh](view_logs.sh)** - Helper script

---

**Now you can easily debug your failed job!** Just run:
```bash
curl -s "http://91.99.14.172:5000/status?hostname=apps-Gie4aema&ip=10.10.10.2&verbose=true" | jq
```

This will show you exactly what went wrong with the Ansible playbook execution. 🔍
