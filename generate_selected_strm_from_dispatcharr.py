#!/usr/bin/env python3
import requests
import os
import sys
import json
import re
from datetime import datetime

# === CONFIGURATION ===
# The base URL of your API service
API_BASE = "http://192.168.178.10:9191"
USERNAME = "STRMgen"
PASSWORD = "STRMgen"
M3U_ACCOUNT_ID = "2"  # Crucial for series stream generation

# Paths for Movies
OUTPUT_DIR_MOVIES = "/mnt/ssd_001/media/VOD_movies_selected"
OUTPUT_DIR_KIDS = "/mnt/ssd_001/media/VOD_kids_movies_selected"
OUTPUT_DIR_UW_MOVIES = "/mnt/ssd_001/media/VOD_uw_movies_selected"

# Paths for Series
OUTPUT_DIR_SERIES = "/mnt/ssd_001/media/VOD_series_selected"
OUTPUT_DIR_KIDS_SERIES = "/mnt/ssd_001/media/VOD_kids_series_selected"
OUTPUT_DIR_UW_SERIES = "/mnt/ssd_001/media/VOD_uw_series_selected"

TOKEN_FILE = "/mnt/ssd_001/dietpi_userdata/IPTV_tools/.strm_token"
# Updated log file name as requested
LOG_FILE = "/mnt/ssd_001/dietpi_userdata/IPTV_tools/log_generate_selected_strm_from_dispatcharr.log"

# ======================

def write_log(message):
    """Writes a message to the log file and maintains a limit of 100 lines."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {message}\n"
    with open(LOG_FILE, "a") as f:
        f.write(log_entry)
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as f:
            lines = f.readlines()
        if len(lines) > 100:
            with open(LOG_FILE, "w") as f:
                f.writelines(lines[-100:])

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

    # Request new token from the API
    try:
        resp = requests.post(
            f"{API_BASE}/api/accounts/token/",
            json={"username": USERNAME, "password": PASSWORD},
            timeout=10
        )
    except requests.exceptions.RequestException:
        print("Network error during login.")
        sys.exit(1)

    if resp.status_code != 200:
        print("Error fetching token:", resp.text)
        sys.exit(1)
    data = resp.json()
    with open(TOKEN_FILE, "w") as f:
        json.dump(data, f)
    return data["access"], data["refresh"]

def request_with_token(method, url, **kwargs):
    """Helper to perform authorized requests and handle token expiration/refresh."""
    access, refresh = get_token()
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {access}"

    try:
        resp = requests.request(method, url, headers=headers, **kwargs)

        if resp.status_code in [401, 403]:
            print(f"Token expired or invalid ({resp.status_code}). Refreshing...")
            if os.path.exists(TOKEN_FILE):
                os.remove(TOKEN_FILE)

            access, refresh = get_token()
            headers["Authorization"] = f"Bearer {access}"
            resp = requests.request(method, url, headers=headers, **kwargs)

        return resp
    except requests.exceptions.RequestException as e:
        print(f"Connection error: {e}")
        return None

def format_title_for_jellyfin(name, year=None):
    """Cleans up the title string to match Jellyfin naming conventions (Folder/File safe)."""
    if not year:
        match = re.search(r"\((\d{4})\)", name)
        if match: year = match.group(1)

    name = re.sub(r"^[A-Z0-9-]{2,10}\s*-\s*", "", name)
    name = re.sub(r"\[.*?\]", "", name)
    name = re.sub(r"\((?!\d{4}).*?\)", "", name)
    garbage = ["1080p", "720p", "4K", "UHD", "German", "Dual", "Dubbed", "BDRip", "WebRip"]
    for word in garbage:
        name = re.sub(word, "", name, flags=re.IGNORECASE)
    name = name.replace(".", " ").replace("_", " ")
    if year and str(year) not in name:
        name = f"{name} ({year})"
    name = re.sub(r"\((\d{4})\)\s*\(\1\)", r"(\1)", name)
    name = re.sub(r"\s{2,}", " ", name).strip(" -")
    safe_name = "".join(c for c in name if c.isalnum() or c in " _-():").rstrip()
    return safe_name

# --- PROVIDER INFO TRIGGER ---

def trigger_provider_info(series_id):
    """Triggers the background retrieval of stream information for the series."""
    url = f"{API_BASE}/api/vod/series/{series_id}/provider-info/"
    print(f"Initializing streams via Provider-Info (ID: {series_id})...")
    resp = request_with_token("GET", url, timeout=60)
    if resp and resp.status_code == 200:
        print("Successfully initialized.")
        return True
    else:
        print(f"Warning: Provider-Info failed or timed out.")
        return False

# --- MOVIE FUNCTIONS ---

def search_movies(name):
    """Searches for movies via API and returns results."""
    resp = request_with_token("GET", f"{API_BASE}/api/vod/movies/?name={name}")
    if not resp or resp.status_code != 200:
        print("Error during search.")
        return []
    return resp.json().get("results", [])

def get_stream_id_movie(movie_id):
    """Retrieves the first available stream provider ID for a movie."""
    resp = request_with_token("GET", f"{API_BASE}/api/vod/movies/{movie_id}/providers/")
    if not resp or resp.status_code != 200:
        print("Error fetching stream data.")
        sys.exit(1)
    providers = resp.json()
    if not providers:
        print("No streams found.")
        sys.exit(1)
    return providers[0].get("stream_id")

def select_variant(variants):
    """User selection menu for found variants (displays ID and name)."""
    print("\nVariants found:")
    for i, v in enumerate(variants, start=1):
        year = v.get("year") or "unknown"
        # Displays ID as requested: e.g., 1) ID:123 | Movie Title
        print(f"{i}) ID:{v['id']} | {v['name']} ({year})")
    print("0) Cancel")
    while True:
        choice = input("Selection: ")
        if choice == "0": sys.exit(0)
        if choice.isdigit() and 1 <= int(choice) <= len(variants):
            return variants[int(choice)-1]

def select_folder_movies():
    """Interactive selection of the movie output directory."""
    print("\n1) VOD_movies_selected")
    print("2) VOD_kids_movies_selected")
    print("3) VOD_uw_movies_selected")
    print("0) Cancel")
    while True:
        c = input("Selection: ")
        if c == "0": sys.exit(0)
        if c == "1": return OUTPUT_DIR_MOVIES
        if c == "2": return OUTPUT_DIR_KIDS
        if c == "3": return OUTPUT_DIR_UW_MOVIES

def generate_strm_movie(movie, stream_id):
    """Creates the final .strm file for a movie."""
    folder = select_folder_movies()
    os.makedirs(folder, exist_ok=True)
    clean_name = format_title_for_jellyfin(movie["name"], movie.get("year"))
    stream_url = f"{API_BASE}/proxy/vod/movie/{movie['uuid']}?stream_id={stream_id}"
    with open(os.path.join(folder, f"{clean_name}.strm"), "w") as f:
        f.write(stream_url)
    print(f"STRM created: {clean_name}")

# --- SERIES FUNCTIONS ---

def search_series(name):
    """Searches for series via API and returns results."""
    resp = request_with_token("GET", f"{API_BASE}/api/vod/series/?name={name}")
    return resp.json().get("results", []) if (resp and resp.status_code == 200) else []

def get_all_episodes(series_id):
    """Retrieves all episodes for a specific series ID from the API."""
    resp = request_with_token("GET", f"{API_BASE}/api/vod/series/{series_id}/episodes/")
    if not resp or resp.status_code != 200: return []
    data = resp.json()
    return data.get("results", data) if isinstance(data, dict) else data

def select_folder_series():
    """Interactive selection of the series output directory."""
    print("\n1) VOD_series_selected")
    print("2) VOD_kids_series_selected")
    print("3) VOD_uw_series_selected")
    print("0) Cancel")
    while True:
        c = input("Selection: ")
        if c == "0": sys.exit(0)
        if c == "1": return OUTPUT_DIR_SERIES
        if c == "2": return OUTPUT_DIR_KIDS_SERIES
        if c == "3": return OUTPUT_DIR_UW_SERIES

def process_series_creation(series_id, series_name, base_folder, silent=False, year=None):
    """Creates directory structure and .strm files for all seasons/episodes of a series."""
    clean_name = format_title_for_jellyfin(series_name, year)
    series_dir = os.path.join(base_folder, clean_name)
    os.makedirs(series_dir, exist_ok=True)

    # Refresh provider streams
    trigger_provider_info(series_id)

    # Persistent ID storage for future update loops
    with open(os.path.join(series_dir, "SteamID.nfo"), "w") as f:
        f.write(str(series_id))

    episodes = get_all_episodes(series_id)
    
    # Requirement 5: Handling cases where provider has no episodes (content removed)
    if not episodes:
        msg = f"Check for: {clean_name} | Warning: No episodes found (ID: {series_id})."
        if not silent: print(msg)
        write_log(msg)
        return 0, 0

    files_updated = 0
    seasons = set()
    for ep in episodes:
        try:
            s, e = str(ep['season_number']).zfill(2), str(ep['episode_number']).zfill(2)
            seasons.add(s)
            s_dir = os.path.join(series_dir, f"Season {s}")
            os.makedirs(s_dir, exist_ok=True)

            filepath = os.path.join(s_dir, f"{clean_name} - S{s}E{e}.strm")
            url = f"{API_BASE}/proxy/vod/episode/{ep['uuid']}?m3u_account_id={M3U_ACCOUNT_ID}"

            # Only write if file is missing or URL has changed
            write = True
            if os.path.exists(filepath):
                with open(filepath, "r") as f:
                    if f.read().strip() == url: write = False
            if write:
                with open(filepath, "w") as f: f.write(url)
                files_updated += 1
        except Exception: continue

    res_msg = f"Check for: {clean_name} | Episodes: {len(episodes)} | Seasons: {len(seasons)} | NEW: {files_updated}"
    if not silent: print(res_msg)
    write_log(res_msg)
    return len(episodes), files_updated

def update_loop():
    """Scans all output directories and updates episodes for all found series."""
    if os.path.exists(TOKEN_FILE):
        os.remove(TOKEN_FILE)
        print("Token refreshed for update run.")

    write_log("--- START UPDATE RUN ---")
    for base_dir in [OUTPUT_DIR_SERIES, OUTPUT_DIR_KIDS_SERIES, OUTPUT_DIR_UW_SERIES]:
        if not os.path.exists(base_dir): continue
        print(f"\n>>> Scanning {os.path.basename(base_dir)}...")
        for entry in os.scandir(base_dir):
            nfo = os.path.join(entry.path, "SteamID.nfo")
            if entry.is_dir() and os.path.exists(nfo):
                try:
                    with open(nfo, "r") as f: s_id = f.read().strip()
                    process_series_creation(s_id, entry.name, base_dir, silent=False)
                except Exception as e:
                    print(f"Error processing {entry.name}: {e}")

    write_log("--- END UPDATE RUN ---")

def main():
    """Main CLI Interface."""
    if len(sys.argv) > 1 and sys.argv[1] == "update":
        update_loop()
        sys.exit(0)

    print("\n=== Dispatcharr STRM Generator ===")
    print("1) Add Movie\n2) Add Series\n3) Update All Series\n0) Exit")
    choice = input("\nSelection: ")

    if choice == "1":
        name = input("Movie Name: ")
        res = search_movies(name)
        if not res:
            print("No results found.")
            sys.exit(0)
        sel = select_variant(res)
        generate_strm_movie(sel, get_stream_id_movie(sel["id"]))

    elif choice == "2":
        name = input("Series Name: ")
        res = search_series(name)
        if not res:
            print("No results found.")
            sys.exit(0)
        sel = select_variant(res)
        process_series_creation(sel['id'], sel['name'], select_folder_series(), year=sel.get('year'))

    elif choice == "3":
        update_loop()

if __name__ == "__main__":
    main()