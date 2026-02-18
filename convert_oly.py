import requests
import re
import urllib3
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from thefuzz import process as fuzzy_process

# Suppress SSL warnings for links with expired certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- Configuration ---
# Downloading the ID list directly from the source to avoid "File Not Found" errors
EPG_DATA_URL = "https://raw.githubusercontent.com/fleung49/star/main/epg_ripper_ALL_SOURCES1.txt"
SOURCE_URL = "https://raw.githubusercontent.com/fleung49/star/refs/heads/main/OLY"
EPG_XML_URL = "https://epgshare01.online/epgshare01/epg_ripper_ALL_SOURCES1.xml.gz"

M3U_FILE = "playlist.m3u"
MD_FILE = "README.md"
MAX_WORKERS = 25 

def normalize_for_epg(name):
    """
    Strips 4K/HD, handles ch/channel, and isolates Call Signs.
    Example: 'WCBS-TV CBS 2' -> 'WCBS'
    """
    clean = name.lower()
    # Remove quality tags
    clean = re.sub(r'\s*\(?4k\)?\s*|\s*\(?hd\)?\s*', '', clean)
    clean = clean.replace('channel', 'ch')
    
    # Isolate Call Sign: look for W or K followed by 2-3 letters
    call_sign_match = re.search(r'\b([k|w][a-z]{2,3})\b', clean)
    if call_sign_match:
        return call_sign_match.group(1).upper()
    
    return clean.strip()

def load_epg_ids():
    """Downloads the ID list directly from the web."""
    try:
        response = requests.get(EPG_DATA_URL, timeout=15)
        response.raise_for_status()
        # Filter out comments and headers
        return [line.strip() for line in response.text.splitlines() if line.strip() and not line.startswith("--")]
    except Exception as e:
        print(f"Warning: Could not load EPG ID list from URL: {e}")
        return []

def check_link(url):
    """Quick check for stream status. verify=False ignores SSL errors."""
    headers = {'User-Agent': 'Mozilla/5.0 (VLC; Win64; x64) AppleWebKit/537.36'}
    try:
        # stream=True ensures we don't download the video, just check the header
        response = requests.get(url, headers=headers, timeout=8, stream=True, allow_redirects=True, verify=False)
        return response.status_code < 400
    except:
        return False

def process_channel(name, url, genre, epg_list):
    """Core logic: Health check -> Grouping -> EPG Mapping."""
    is_active = check_link(url)
    
    # 1. Grouping Logic
    if "s.rocketdns.info:8080" in url:
        group = "Rocket"
    elif not is_active:
        group = "Offline"
    else:
        group = genre

    # 2. EPG Matching (Call-Sign Priority)
    best_match = ""
    if epg_list:
        search_term = normalize_for_epg(name)
        # Match the cleaned name/callsign against the EPG ID list
        match, score = fuzzy_process.extractOne(search_term, epg_list)
        if score > 70:
            best_match = match
        
    return {
        "name": name, "url": url, "group": group, 
        "active": is_active, "tvg_id": best_match
    }

def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Loading EPG database...")
    epg_ids = load_epg_ids()
    
    try:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Fetching OLY source...")
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

        print(f"[{datetime.now().strftime('%H:%M:%S')}] Scanning {len(channels_to_check)} channels...")
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            results = list(executor.map(lambda p: process_channel(*p, epg_ids), channels_to_check))

        # Generate M3U
        m3u_lines = [f'#EXTM3U x-tvg-url="{EPG_XML_URL}"']
        for res in results:
            m3u_lines.append(f'#EXTINF:-1 tvg-id="{res["tvg_id"]}" group-title="{res["group"]}",{res["name"]}')
            m3u_lines.append(res["url"])
            
        # Generate Markdown Status Dashboard
        md_lines = ["# 📺 Channel Status Dashboard", 
                    f"**Last Sync:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC\n", 
                    "| Status | Channel | Group | EPG ID |", 
                    "| :---: | :--- | :--- | :--- |"]
        for res in results:
            icon = "✅" if res["active"] else "❌"
            md_lines.append(f"| {icon} | {res['name']} | {res['group']} | `{res['tvg_id']}` |")

        with open(M3U_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(m3u_lines))
        with open(MD_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(md_lines))
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Successfully updated playlist and dashboard.")

    except Exception as e:
        print(f"Error in main loop: {e}")

if __name__ == "__main__":
    main()
