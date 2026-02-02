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
# Script to run after refresh (can be set with or without .py extension)
STRM_SCRIPT_PATH = "/mnt/ssd_001/dietpi_userdata/IPTV_tools/generate_selected_strm_from_dispatcharr.py"
TOKEN_FILE = "/mnt/ssd_001/dietpi_userdata/IPTV_tools/.strm_token"

# Log file for this refresh cycle
LOG_FILE = "/mnt/ssd_001/dietpi_userdata/IPTV_tools/log_refresh_m3u_in_dispatcharr_and_update_strms.log"

# Wait time after triggering the refresh in seconds (e.g. 180s = 3 minutes)
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

def load_tokens():
    """Loads access and refresh tokens from the local file."""
    if not os.path.exists(TOKEN_FILE):
        return None
    try:
        with open(TOKEN_FILE, "r") as f:
            data = json.load(f)
        if "access" not in data or "refresh" not in data:
            return None
        return data
    except (json.JSONDecodeError, IOError):
        return None

def get_token():
    """Retrieves a new token via login or returns existing ones."""
    tokens = load_tokens()
    if tokens:
        return tokens["access"], tokens["refresh"]

    # Request new token from the API if no file exists
    try:
        resp = requests.post(
            f"{API_BASE}/api/accounts/token/",
            json={"username": USERNAME, "password": PASSWORD},
            timeout=10
        )
    except requests.exceptions.RequestException:
        write_log("Network error during login.")
        return None, None

    if resp.status_code != 200:
        write_log(f"Error fetching token: {resp.text}")
        return None, None

    data = resp.json()
    with open(TOKEN_FILE, "w") as f:
        json.dump(data, f)
    return data["access"], data["refresh"]

def request_with_token(method, url, **kwargs):
    """
    Helper to perform authorized requests and handle token expiration/refresh automatically.
    This ensures we don't fail on a 401 error but retry with a new token.
    """
    access, refresh = get_token()
    if not access:
        return None

    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {access}"
    # Ensure we accept JSON responses
    headers["accept"] = "application/json"

    try:
        resp = requests.request(method, url, headers=headers, **kwargs)

        # If token is expired (401) or forbidden (403), try to refresh it
        if resp.status_code in [401, 403]:
            write_log(f"Token expired or invalid ({resp.status_code}). Refreshing...")
            
            # Remove the old invalid token file
            if os.path.exists(TOKEN_FILE):
                os.remove(TOKEN_FILE)

            # Get fresh tokens
            access, refresh = get_token()
            if not access:
                return None
            
            # Retry the request with the new token
            headers["Authorization"] = f"Bearer {access}"
            resp = requests.request(method, url, headers=headers, **kwargs)

        return resp
    except requests.exceptions.RequestException as e:
        write_log(f"Connection error: {e}")
        return None

def trigger_refresh():
    """Triggers the M3U refresh via POST request using the authorized helper."""
    url = f"{API_BASE}/api/m3u/refresh/"
    write_log(f"Sending POST Refresh to: {url}")
    
    # POST Request with empty body (data='') as often required by Swagger implementations
    # Using request_with_token handles the 401 retry logic automatically
    resp = request_with_token("POST", url, data='', timeout=30)

    # Check for successful status codes (200 OK, 201 Created, 202 Accepted, 204 No Content)
    if resp and resp.status_code in [200, 201, 202, 204]:
        write_log(f"M3U Refresh successfully triggered (Status {resp.status_code}).")
        return True
    else:
        status = resp.status_code if resp else "No Response"
        text = resp.text if resp else ""
        write_log(f"Refresh failed. Code: {status} - {text}")
        return False

def run_strm_update():
    """Executes the STRM generation script and captures output in real-time."""
    target_path = STRM_SCRIPT_PATH
    
    # Safety check: Try finding the script with .py extension if the path is missing it
    if not os.path.exists(target_path):
        if os.path.exists(target_path + ".py"):
            target_path += ".py"
        else:
            write_log(f"ERROR: STRM script not found at: {STRM_SCRIPT_PATH}")
            return

    write_log(f"Starting STRM Update: {os.path.basename(target_path)}")
    try:
        # Launch subprocess and merge stderr into stdout for unified logging
        process = subprocess.Popen(
            ["/usr/bin/python3", target_path, "update"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1 # Line buffered
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
        # Pause execution to allow Dispatcharr to process the M3U list background tasks
        time.sleep(WAIT_TIME)
        
        # Second step: Run the STRM generator in update mode
        run_strm_update()
    else:
        write_log("Aborting: Could not start M3U refresh.")

    write_log("=== END REFRESH CYCLE ===")

if __name__ == "__main__":
    main()
