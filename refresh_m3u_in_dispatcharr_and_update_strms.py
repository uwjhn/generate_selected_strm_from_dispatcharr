#!/usr/bin/env python3
import requests
import time
import subprocess
import os
import sys
import json
from datetime import datetime

# === CONFIGURATION ===
# Base URL of the Dispatcharr API
API_BASE = "http://192.168.178.10:9191"
USERNAME = "STRMgen"
PASSWORD = "STRMgen"

# Paths to the associated scripts and files
STRM_SCRIPT_PATH = "/mnt/ssd_001/dietpi_userdata/IPTV_tools/generate_selected_strm_from_dispatcharr"
TOKEN_FILE = "/mnt/ssd_001/dietpi_userdata/IPTV_tools/.strm_token"

# Updated log file name as requested
LOG_FILE = "/mnt/ssd_001/dietpi_userdata/IPTV_tools/log_refresh_m3u_in_dispatcharr_and_update_strms.log"

# Wait time after triggering the refresh in seconds (3 minutes)
# This allows the background database update to complete before scanning for new episodes
WAIT_TIME = 180

# ======================

def write_log(message):
    """Writes logs with a timestamp, prints to console, and rotates at 100 lines."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {message}\n"

    # Immediate console output for monitoring
    print(log_entry.strip())

    try:
        with open(LOG_FILE, "a") as f:
            f.write(log_entry)

        # Log rotation: Keep only the last 100 lines to prevent file bloat
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, "r") as f:
                lines = f.readlines()
            if len(lines) > 100:
                with open(LOG_FILE, "w") as f:
                    f.writelines(lines[-100:])
    except Exception as e:
        print(f"Error writing to log file: {e}")

def get_token():
    """Retrieves access token from local file or authenticates via API if needed."""
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, "r") as f:
                data = json.load(f)
            if "access" in data:
                return data["access"]
        except Exception:
            pass

    write_log("Token not found or invalid. Authenticating...")
    try:
        resp = requests.post(
            f"{API_BASE}/api/accounts/token/",
            json={"username": USERNAME, "password": PASSWORD},
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            with open(TOKEN_FILE, "w") as f:
                json.dump(data, f)
            return data["access"]
        else:
            write_log(f"Login failed: {resp.status_code}")
            return None
    except Exception as e:
        write_log(f"Connection error during login: {e}")
        return None

def trigger_refresh():
    """Triggers the M3U refresh in Dispatcharr via POST request."""
    token = get_token()
    if not token:
        return False

    url = f"{API_BASE}/api/m3u/refresh/"
    headers = {
        "Authorization": f"Bearer {token}",
        "accept": "application/json",
        "Content-Length": "0"
    }

    write_log(f"Sending POST Refresh to: {url}")
    try:
        # POST Request with empty body (as required by Swagger UI)
        resp = requests.post(url, headers=headers, data='', timeout=30)

        if resp.status_code in [200, 201, 202, 204]:
            write_log(f"M3U Refresh successfully triggered (Status {resp.status_code}).")
            return True
        else:
            write_log(f"Refresh failed. Code: {resp.status_code} - {resp.text}")
            return False
    except Exception as e:
        write_log(f"Error during refresh request: {e}")
        return False

def run_strm_update():
    """Executes the STRM generation script and captures output in real-time."""
    # Safety check: Try both with and without .py extension if the path fails
    target_path = STRM_SCRIPT_PATH
    if not os.path.exists(target_path):
        if os.path.exists(target_path + ".py"):
            target_path += ".py"
        else:
            write_log(f"ERROR: STRM script not found: {STRM_SCRIPT_PATH}")
            return

    write_log(f"Starting STRM Update: {os.path.basename(target_path)}")
    try:
        # Launch subprocess and merge stderr into stdout
        process = subprocess.Popen(
            ["/usr/bin/python3", target_path, "update"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        # Stream lines from the generator script into this script's log
        for line in process.stdout:
            clean_line = line.strip()
            if clean_line:
                write_log(f" > {clean_line}")

        process.wait()

        if process.returncode == 0:
            write_log("STRM script completed successfully.")
        else:
            write_log(f"STRM script finished with errors (Exit Code {process.returncode}).")

    except Exception as e:
        write_log(f"Critical error executing sub-script: {e}")

def main():
    """Main execution cycle: Refresh -> Wait -> Update."""
    write_log("=== START REFRESH CYCLE ===")

    # First step: Trigger the provider refresh
    if trigger_refresh():
        write_log(f"Waiting {WAIT_TIME} seconds for database update to settle...")
        # Pause execution to allow Dispatcharr to process the M3U list
        time.sleep(WAIT_TIME)
        
        # Second step: Run the STRM generator in update mode
        run_strm_update()
    else:
        write_log("Aborting: Could not start M3U refresh.")

    write_log("=== END REFRESH CYCLE ===")

if __name__ == "__main__":
    main()