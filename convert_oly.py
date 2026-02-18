import requests
import re
import urllib3
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from thefuzz import process as fuzzy_process

# Suppress SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configuration
SOURCE_URL = "https://raw.githubusercontent.com/fleung49/star/refs/heads/main/OLY"
EPG_XML_URL = "https://epgshare01.online/epgshare01/epg_ripper_ALL_SOURCES1.xml.gz"
# Since you haven't uploaded the .txt to root, I'm fetching it from your known repo
EPG_DATA_URL = "https://raw.githubusercontent.com/fleung49/star/main/epg_ripper_ALL_SOURCES1.txt"

M3U_FILE = "playlist.m3u"
MD_FILE = "README.md"
MAX_WORKERS = 25 

def get_epg_id(channel_name, epg_list):
    """
    Improved Mapping Logic:
    1. Extracts Call Sign (KCBS, WABC, etc.)
    2. Searches EPG list for IDs containing that Call Sign
    """
    # Clean name for searching
    name_clean = channel_name.upper()
    
    # 1. Try to extract Call Sign (4 letters starting with K or W)
    match = re.search(r'\b([K|W][A-Z]{2,3})\b', name_clean)
    if match:
        call_sign = match.group(1)
        # Look for exact prefix match in EPG list (e.g., "KCBS.us")
        for epg_id in epg_list:
            if epg_id.upper().startswith(f"{call_sign}."):
                return epg_id

    # 2. Fallback: Fuzzy match if no call sign found
    # We strip common suffixes to improve matching
    stripped_name = re.sub(r'\(.*?\)|-TV|HD|4K', '', name_clean).strip()
    match, score = fuzzy_process.extractOne(stripped_name, epg_list)
    if score > 75:
        return match
        
    return ""

def load_epg_ids():
    try:
        response = requests.get(EPG_DATA_URL, timeout=10)
        return [line.strip() for line in response.text.splitlines() if line.strip() and not line.startswith("--")]
    except:
        return []

def check_link(url):
    headers = {'User-Agent': 'Mozilla/5.0 (VLC; Win64; x64)'}
    try:
        response = requests.get(url, headers=headers, timeout=7, stream=True, verify=False)
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

    # Smart EPG ID Assignment
    tvg_id = get_epg_id(name, epg_list)
        
    return {
        "name": name, "url": url, "group": group, 
        "active": is_active, "tvg_id": tvg_id
    }

def main():
    print("Loading EPG database and channel list...")
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
                name, url = line.split(",", 1)
                channels_to_check.append((name.strip(), url.strip(), current_genre))

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            results = list(executor.map(lambda p: process_channel(*p, epg_ids), channels_to_check))

        # Write M3U
        m3u_lines = [f'#EXTM3U x-tvg-url="{EPG_XML_URL}"']
        for res in results:
            m3u_lines.append(f'#EXTINF:-1 tvg-id="{res["tvg_id"]}" group-title="{res["group"]}",{res["name"]}')
            m3u_lines.append(res["url"])
            
        # Write README
        md_lines = ["# 📺 Channel Status Dashboard", f"**Last Updated:** {datetime.now()} UTC\n", 
                    "| Status | Channel | Group | EPG Match |", "| :---: | :--- | :--- | :--- |"]
        for res in results:
            icon = "✅" if res["active"] else "❌"
            md_lines.append(f"| {icon} | {res['name']} | {res['group']} | `{res['tvg_id']}` |")

        with open(M3U_FILE, "w", encoding="utf-8") as f: f.write("\n".join(m3u_lines))
        with open(MD_FILE, "w", encoding="utf-8") as f: f.write("\n".join(md_lines))
        print("Playlist generated with mapped tvg-ids.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
