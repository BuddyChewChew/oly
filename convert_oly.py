import requests
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from thefuzz import fuzz, process

# --- Configuration ---
SOURCE_URL = "https://raw.githubusercontent.com/fleung49/star/refs/heads/main/OLY"
EPG_XML_URL = "https://epgshare01.online/epgshare01/epg_ripper_ALL_SOURCES1.xml.gz"
# CORRECTED URL BELOW
EPG_DATA_URL = "https://epgshare01.online/epgshare01/epg_ripper_ALL_SOURCES1.txt"

M3U_FILE = "playlist.m3u"
MD_FILE = "README.md"
MAX_WORKERS = 30 

def super_clean(text):
    """
    Standardizes names for matching.
    'ABC.News.Live.us2' -> 'abcnewslive'
    'ABC News Live' -> 'abcnewslive'
    """
    if not text: return ""
    text = text.lower()
    # Remove common EPG suffixes (.us2, .ca, etc)
    text = re.sub(r'\.[a-z]{2,3}\d?$', '', text)
    # Remove all non-alphanumeric characters
    return re.sub(r'[^a-z0-9]', '', text)

def find_best_epg_match(channel_name, epg_list):
    """
    Matches playlist name to EPG ID list.
    """
    if not channel_name or not epg_list:
        return ""
    
    target = super_clean(channel_name)
    
    # 1. Immediate match for cleaned strings
    for original_id in epg_list:
        if target == super_clean(original_id):
            return original_id
            
    # 2. Fuzzy fallback
    match, score = process.extractOne(target, epg_list, scorer=fuzz.token_set_ratio)
    
    return match if score > 75 else ""

def load_epg_database():
    """Downloads the actual epgshare01 ID list."""
    try:
        r = requests.get(EPG_DATA_URL, timeout=15)
        r.raise_for_status()
        # Filter for valid IDs
        return [l.strip() for l in r.text.splitlines() if l.strip() and not l.startswith("--")]
    except Exception as e:
        print(f"Error loading EPG list: {e}")
        return []

def check_link(url):
    """Strict SSL connection check."""
    headers = {'User-Agent': 'Mozilla/5.0 (VLC; Win64; x64)'}
    try:
        r = requests.get(url, headers=headers, timeout=5, stream=True)
        return r.status_code < 400
    except:
        return False

def process_channel(name, url, genre, epg_list):
    active = check_link(url)
    
    # Rocket Grouping
    if "s.rocketdns.info:8080" in url:
        group = "Rocket"
    elif not active:
        group = "Offline"
    else:
        group = genre

    return {
        "name": name, "url": url, "group": group, 
        "active": active, "tvg_id": find_best_epg_match(name, epg_list)
    }

def main():
    print(f"Downloading EPG list from {EPG_DATA_URL}...")
    epg_list = load_epg_database()
    print(f"Loaded {len(epg_list)} EPG IDs.")
    
    try:
        r = requests.get(SOURCE_URL)
        r.raise_for_status()
        lines = r.text.splitlines()
        
        channels = []
        current_genre = "General"

        for l in lines:
            l = l.strip()
            if not l or l.startswith("#"): continue
            if ",#genre#" in l:
                current_genre = l.split(",")[0].strip()
                continue
            if "," in l:
                name, url = l.split(",", 1)
                channels.append((name.strip(), url.strip(), current_genre))

        print(f"Processing {len(channels)} channels...")
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            results = list(executor.map(lambda p: process_channel(*p, epg_list), channels))

        # Build M3U
        with open(M3U_FILE, "w", encoding="utf-8") as f:
            f.write(f'#EXTM3U x-tvg-url="{EPG_XML_URL}"\n')
            for res in results:
                f.write(f'#EXTINF:-1 tvg-id="{res["tvg_id"]}" group-title="{res["group"]}",{res["name"]}\n')
                f.write(f'{res["url"]}\n')

        # Build README Dashboard
        with open(MD_FILE, "w", encoding="utf-8") as f:
            f.write("# 📺 Channel Status Dashboard\n\n")
            f.write(f"**Last Update:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC\n\n")
            f.write("| Status | Channel | Group | EPG Match |\n| :---: | :--- | :--- | :--- |\n")
            for res in results:
                icon = "✅" if res["active"] else "❌"
                f.write(f"| {icon} | {res['name']} | {res['group']} | `{res['tvg_id']}` |\n")
        
        print("Playlist and Dashboard successfully updated.")

    except Exception as e:
        print(f"Critical Error: {e}")

if __name__ == "__main__":
    main()
