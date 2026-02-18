import requests
import re
import urllib3
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# Suppress SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configuration
SOURCE_URL = "https://raw.githubusercontent.com/fleung49/star/refs/heads/main/OLY"
EPG_XML_URL = "https://epgshare01.online/epgshare01/epg_ripper_ALL_SOURCES1.xml.gz"
EPG_DATA_URL = "https://raw.githubusercontent.com/fleung49/star/main/epg_ripper_ALL_SOURCES1.txt"

M3U_FILE = "playlist.m3u"
MD_FILE = "README.md"
MAX_WORKERS = 25 

def normalize(text):
    """
    Strips text for fuzzy matching.
    Example: 'KCBS-TV CBS 2' -> 'kcbstvcbs2'
             'KCBS.us2' -> 'kcbs'
    """
    if not text: return ""
    text = text.lower()
    # Remove common EPG suffixes like .us, .us2, .ca, .uk
    text = re.sub(r'\.[a-z]{2,3}\d?$', '', text)
    # Remove dots and special characters
    return re.sub(r'[^a-z0-9]', '', text)

def find_match(channel_name, epg_list):
    """Matches by comparing normalized strings."""
    c_norm = normalize(channel_name)
    
    # 1. Look for a starting match (Call Signs)
    # Extracts first 4 letters if it starts with K or W
    call_sign = re.match(r'^[kw][a-z]{2,3}', c_norm)
    if call_sign:
        cs = call_sign.group(0)
        for e_id in epg_list:
            if normalize(e_id).startswith(cs):
                return e_id

    # 2. General containment match
    for e_id in epg_list:
        e_norm = normalize(e_id)
        if e_norm and (e_norm in c_norm or c_norm in e_norm):
            return e_id
            
    return ""

def load_epg():
    try:
        r = requests.get(EPG_DATA_URL, timeout=10)
        return [l.strip() for l in r.text.splitlines() if l.strip() and not l.startswith("--")]
    except:
        return []

def check_url(url):
    headers = {'User-Agent': 'Mozilla/5.0 (VLC)'}
    try:
        r = requests.get(url, headers=headers, timeout=5, stream=True, verify=False)
        return r.status_code < 400
    except:
        return False

def process(name, url, genre, epg_list):
    active = check_url(url)
    
    # Grouping Logic
    if "s.rocketdns.info:8080" in url:
        group = "Rocket"
    elif not active:
        group = "Offline"
    else:
        group = genre

    return {
        "name": name, "url": url, "group": group, 
        "active": active, "tvg_id": find_match(name, epg_list)
    }

def main():
    print("Fetching EPG database...")
    epg_list = load_epg()
    
    try:
        r = requests.get(SOURCE_URL)
        lines = r.text.splitlines()
        channels = []
        genre = "General"

        for l in lines:
            l = l.strip()
            if not l: continue
            if ",#genre#" in l:
                genre = l.split(",")[0].strip()
                continue
            if "," in l:
                name, url = l.split(",", 1)
                channels.append((name.strip(), url.strip(), genre))

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            results = list(executor.map(lambda p: process(*p, epg_list), channels))

        # Write M3U
        with open(M3U_FILE, "w", encoding="utf-8") as f:
            f.write(f'#EXTM3U x-tvg-url="{EPG_XML_URL}"\n')
            for res in results:
                f.write(f'#EXTINF:-1 tvg-id="{res["tvg_id"]}" group-title="{res["group"]}",{res["name"]}\n')
                f.write(f'{res["url"]}\n')

        # Write README
        with open(MD_FILE, "w", encoding="utf-8") as f:
            f.write("# 📺 Channel Status\n\n| Status | Channel | Group | EPG Match |\n| :---: | :--- | :--- | :--- |\n")
            for res in results:
                icon = "✅" if res["active"] else "❌"
                f.write(f"| {icon} | {res['name']} | {res['group']} | `{res['tvg_id']}` |\n")
        
        print("Update complete.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
