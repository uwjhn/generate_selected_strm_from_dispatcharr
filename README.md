# Dispatcharr STRM Generator for Jellyfin

This project provides a surgical way to manage your VOD library from [Dispatcharr](https://github.com/Dispatcharr/Dispatcharr). Instead of importing thousands of unwanted streams into your media server, these scripts allow you to selectively pick movies and series, generating .strm files that Jellyfin can play directly. All designed to run in a terminal, e.g. via ssh on a smartphone.

---

## Prerequisites

1. Dispatcharr: Must be installed and running with VOD support active.
2. M3U Settings: In Dispatcharr, disable automatic M3U updates. This prevents database locks and ensures the scripts control the refresh timing.
3. API User: Create a separate Admin user in Dispatcharr (default in scripts is STRMgen) to allow API authentication via tokens.
4. Environment: Python 3.x installed on your system.

---

## Jellyfin Integration

The scripts organize content into specific directories. You should add these root folders as libraries in Jellyfin.

| Media Type | Destination Folders (Examples) | Jellyfin Library Type |
| :--- | :--- | :--- |
| Movies | VOD_movies_selected, VOD_kids_movies_selected, ... | Movies |
| Series | VOD_series_selected, VOD_kids_series_selected, ... | Shows |

---

## Usage

### 1. Manual Addition: generate_selected_strm_from_dispatcharr.py
Use this script whenever you want to add a new movie or series to your collection.

```
python3 generate_selected_strm_from_dispatcharr.py
```

- Add Movie/Series: Search by name, select the correct version from the results, and choose the target directory.
- Update All: You can also trigger a manual update of all existing series from the menu.
- Internal logic: For series, it creates a SteamID.nfo file for tracking. This allows the update script to identify the series in the API later.

### 2. Automatic Maintenance: refresh_m3u_in_dispatcharr.py
This script automates the background maintenance. It is designed to be run via a scheduler (like Cron).

```
python3 refresh_m3u_in_dispatcharr.py
```

Execution Flow:
1. Trigger: Sends a POST request to Dispatcharr to start an M3U provider refresh.
2. Wait: Pauses for 180 seconds to allow the database to update (the delay/wait can be shortened, based on your M3U provider and hardware).
3. Sync: Automatically calls the generator script in update mode to add new episodes.

---

## Configuration

Open both .py files and edit the CONFIGURATION section:

```
API_BASE = "http://192.168.178.10:9191"
USERNAME = "STRMgen"
PASSWORD = "STRMgen"

OUTPUT_DIR_MOVIES - e.g. = "/mnt/ssd_001/media/VOD_movies_selected"
OUTPUT_DIR_SERIES - e.g. = "/mnt/ssd_001/media/VOD_series_selected"
```

---

## Automation (Cronjob)
To keep your series updated automatically (e.g., every night at 4:00 AM):
```
0 4 * * * /usr/bin/python3 /path/to/refresh_m3u_in_dispatcharr.py
```

---

## Logging
Both scripts maintain rolling logs (max 100 lines) to help you monitor the activity:
- log_generate_selected_strm_from_dispatcharr.log
- log_refresh_m3u_in_dispatcharr_and_update_strms.log