import requests
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from thefuzz import process as fuzzy_process

# Configuration
SOURCE_URL = "https://raw.githubusercontent.com/fleung49/star/refs/heads/main/OLY"
EPG_URL = "https://epgshare01.online/epgshare01/epg_ripper_ALL_SOURCES1.xml.gz"
EPG_DATA_FILE = "epg_ripper_ALL_SOURCES1.txt"
M3U_FILE = "playlist.m3u"
MD_FILE = "README.md"
MAX_WORKERS = 25 

def normalize_name(name):
    """
    Combines logic from your patcher and our call-sign logic.
    Removes 4k/hd, handles ch/channel, and extracts Call Signs.
    """
    name = name.lower()
    name = re.sub(r'\s*\(?4k\)?\s*|\s*\(?hd\)?\s*', '', name)
    name = name.replace('channel', 'ch')
    
    # Extract Call Sign (e.g., WCBS from WCBS-TV)
    call_match = re.search(r'\b([w|k][a-z]{2,3})\b', name)
    if call_match:
        return call_match.group(1).upper()
    return name.strip()

def load_epg_ids():
    try:
        with open(EPG_DATA_FILE, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip() and not line.startswith("--")]
    except FileNotFoundError:
        return []

def check_link(url):
    headers = {'User-Agent': 'Mozilla/5.0 (VLC; Win64; x64)'}
    try:
        response = requests.get(url, headers=headers, timeout=7, stream=True, allow_redirects=True)
        return response.status_code < 400
    except:
        return False

def process_channel(name, url, genre, epg_list):
    is_active = check_link(url)
    
    # Grouping
    if "s.rocketdns.info:8080" in url:
        group = "Rocket"
    elif not is_active:
        group = "Offline"
    else:
        group = genre

    # Enhanced Mapping
    best_match = ""
    if epg_list:
        search_term = normalize_name(name)
        match, score = fuzzy_process.extractOne(search_term, epg_list)
        # Higher score requirement for better accuracy
        if score > 70:
            best_match = match
        
    return {
        "name": name, "url": url, "group": group, 
        "active": is_active, "tvg_id": best_match
    }

def main():
    epg_ids = load_epg_ids()
    try:
        response = requests.get(SOURCE_URL)
        response.raise_for_status()
        lines = response.text.splitlines()

        channels_to_check = []
        current_genre = "General"

        for line in lines:
            line = line.strip()
            if not line: continue
            if ",#genre#" in line:
                current_genre = line.split(",")[0].strip()
                continue
            if "," in line:
                parts = line.split(",", 1)
                channels_to_check.append((parts[0].strip(), parts[1].strip(), current_genre))

        print(f"Syncing {len(channels_to_check)} channels...")
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            results = list(executor.map(lambda p: process_channel(*p, epg_ids), channels_to_check))

        # M3U Header (Using the x-tvg-url from your patcher request)
        m3u_lines = [f'#EXTM3U x-tvg-url="{EPG_URL}"']
        for res in results:
            m3u_lines.append(f'#EXTINF:-1 tvg-id="{res["tvg_id"]}" group-title="{res["group"]}",{res["name"]}')
            m3u_lines.append(res["url"])
            
        # Markdown Dashboard
        md_lines = ["# 📺 Channel Status Dashboard", f"**Last Updated:** {datetime.now()} UTC\n", 
                    "| Status | Channel | Group | EPG Match |", "| :---: | :--- | :--- | :--- |"]
        for res in results:
            icon = "✅" if res["active"] else "❌"
            md_lines.append(f"| {icon} | {res['name']} | {res['group']} | `{res['tvg_id']}` |")

        with open(M3U_FILE, "w", encoding="utf-8") as f: f.write("\n".join(m3u_lines))
        with open(MD_FILE, "w", encoding="utf-8") as f: f.write("\n".join(md_lines))
        print("Success: Playlist patched and status dashboard updated.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
