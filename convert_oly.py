import requests
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from thefuzz import fuzz, process

# --- Configuration ---
SOURCE_URL = "https://raw.githubusercontent.com/fleung49/star/refs/heads/main/OLY"
EPG_XML_URL = "https://epgshare01.online/epgshare01/epg_ripper_ALL_SOURCES1.xml.gz"
EPG_DATA_URL = "https://epgshare01.online/epgshare01/epg_ripper_ALL_SOURCES1.txt"

M3U_FILE = "playlist.m3u"
MD_FILE = "README.md"
MAX_WORKERS = 30 

def find_best_epg_match(channel_name, epg_list):
    """
    Two-step matching:
    1. Naked string comparison (ignores dots/spaces).
    2. Fuzzy matching fallback.
    """
    if not channel_name or not epg_list:
        return ""
    
    # Clean the playlist name
    name_clean = re.sub(r'\(.*?\)', '', channel_name.lower()) # Remove (City)
    name_clean = re.sub(r'[^a-z0-9]', '', name_clean) # Remove all symbols
    
    # 1. Direct Search: Naked comparison
    for e_id in epg_list:
        clean_eid = re.sub(r'[^a-z0-9]', '', e_id.lower())
        if name_clean == clean_eid or name_clean in clean_eid:
            return e_id

    # 2. Fuzzy Search: Fallback for complex names
    match, score = process.extractOne(channel_name, epg_list, scorer=fuzz.token_set_ratio)
    
    return match if score > 65 else ""

def load_epg_database():
    """Downloads the ID list using a browser-like User-Agent."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        r = requests.get(EPG_DATA_URL, headers=headers, timeout=20)
        r.raise_for_status()
        return [l.strip() for l in r.text.splitlines() if l.strip() and not l.startswith("--")]
    except Exception as e:
        print(f"Error loading EPG list: {e}")
        return []

def check_link(url):
    """Strict SSL connection check."""
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        r = requests.get(url, headers=headers, timeout=5, stream=True)
        return r.status_code < 400
    except:
        return False

def process_channel(name, url, genre, epg_list):
    active = check_link(url)
    
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
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Downloading EPG database...")
    epg_list = load_epg_database()
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Loaded {len(epg_list)} EPG IDs.")
    
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

        print(f"[{datetime.now().strftime('%H:%M:%S')}] Processing {len(channels)} channels...")
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            results = list(executor.map(lambda p: process_channel(*p, epg_list), channels))

        # Build M3U
        with open(M3U_FILE, "w", encoding="utf-8") as f:
            f.write(f'#EXTM3U x-tvg-url="{EPG_XML_URL}"\n')
            for res in results:
                f.write(f'#EXTINF:-1 tvg-id="{res["tvg_id"]}" group-title="{res["group"]}",{res["name"]}\n')
                f.write(f'{res["url"]}\n')

        # Build README
        with open(MD_FILE, "w", encoding="utf-8") as f:
            f.write("# 📺 Channel Status Dashboard\n\n")
            f.write(f"**Last Update:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC\n\n")
            f.write("| Status | Channel | Group | EPG Match |\n| :---: | :--- | :--- | :--- |\n")
            for res in results:
                icon = "✅" if res["active"] else "❌"
                f.write(f"| {icon} | {res['name']} | {res['group']} | `{res['tvg_id']}` |\n")
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Successfully updated all files.")

    except Exception as e:
        print(f"Critical Error: {e}")

if __name__ == "__main__":
    main()
