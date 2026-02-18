import requests
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from thefuzz import process as fuzzy_process

# Configuration & URLs
SOURCE_URL = "https://raw.githubusercontent.com/fleung49/star/refs/heads/main/OLY"
EPG_URL = "https://epgshare01.online/epgshare01/epg_ripper_ALL_SOURCES1.xml.gz"
EPG_DATA_FILE = "epg_ripper_ALL_SOURCES1.txt"
M3U_FILE = "playlist.m3u"
MD_FILE = "README.md"
MAX_WORKERS = 25 

def clean_for_epg(name):
    """
    Extracts the Call Sign for matching while keeping it intact.
    Example: 'WCBS-TV CBS 2' -> 'WCBS'
    """
    # 1. Try to find a 4-letter call sign starting with W or K
    call_sign_match = re.search(r'\b([W|K][A-Z]{2,3})\b', name.upper())
    if call_sign_match:
        return call_sign_match.group(1)
    
    # 2. Fallback: remove parentheses and extra whitespace
    return re.sub(r'\(.*?\)', '', name).strip()

def load_epg_ids():
    """Loads IDs from the text file you uploaded."""
    try:
        with open(EPG_DATA_FILE, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip() and not line.startswith("--")]
    except FileNotFoundError:
        print("EPG File not found. Run without mapping.")
        return []

def check_link(url):
    """Fast check using GET stream to avoid false negatives."""
    headers = {'User-Agent': 'Mozilla/5.0 (VLC; Win64; x64)'}
    try:
        response = requests.get(url, headers=headers, timeout=7, stream=True, allow_redirects=True)
        return response.status_code < 400
    except:
        return False

def process_channel(name, url, genre, epg_list):
    """Handles logic for a single channel entry."""
    is_active = check_link(url)
    
    # Grouping Logic
    if "s.rocketdns.info:8080" in url:
        group = "Rocket"
    elif not is_active:
        group = "Offline"
    else:
        group = genre

    # EPG Matching Logic
    best_match = ""
    if epg_list:
        search_term = clean_for_epg(name)
        # Match call sign against EPG list
        match, score = fuzzy_process.extractOne(search_term, epg_list)
        if score > 50: 
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
            if not line or ",#genre#" in line:
                if ",#genre#" in line: current_genre = line.split(",")[0]
                continue
            if "," in line:
                parts = line.split(",", 1)
                channels_to_check.append((parts[0].strip(), parts[1].strip(), current_genre))

        print(f"Processing {len(channels_to_check)} channels...")
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            results = list(executor.map(lambda p: process_channel(*p, epg_ids), channels_to_check))

        # Generate M3U with EPG Header
        m3u_lines = [f'#EXTM3U x-tvg-url="{EPG_URL}"']
        for res in results:
            m3u_lines.append(f'#EXTINF:-1 tvg-id="{res["tvg_id"]}" group-title="{res["group"]}",{res["name"]}')
            m3u_lines.append(res["url"])
            
        # Generate Markdown Status Dashboard
        md_lines = ["# 📺 Channel Status Dashboard", f"**Last Sync:** {datetime.now()} UTC\n", 
                    "| Status | Channel | Group | EPG Match |", "| :---: | :--- | :--- | :--- |"]
        for res in results:
            icon = "✅" if res["active"] else "❌"
            md_lines.append(f"| {icon} | {res['name']} | {res['group']} | `{res['tvg_id']}` |")

        with open(M3U_FILE, "w", encoding="utf-8") as f: f.write("\n".join(m3u_lines))
        with open(MD_FILE, "w", encoding="utf-8") as f: f.write("\n".join(md_lines))
        print("Success: M3U and README updated.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
