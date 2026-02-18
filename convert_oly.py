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

def simplify(text):
    """
    Cleans names for comparison.
    Example: 'A.and.E.HD.East.us2' -> 'aandehdeast'
             'A & E HD East' -> 'aandehdeast'
    """
    if not text: return ""
    text = text.lower()
    # Remove .us2, .ae, etc. at the end
    text = re.sub(r'\.[a-z]{2,3}\d?$', '', text)
    # Remove dots, dashes, parentheses, and spaces
    text = re.sub(r'[^a-z0-9]', '', text)
    return text

def find_best_match(channel_name, epg_dict):
    """
    Compares the simplified channel name against the simplified EPG database.
    """
    simple_name = simplify(channel_name)
    
    # 1. Look for exact simplified match
    if simple_name in epg_dict:
        return epg_dict[simple_name]
    
    # 2. Look for Call Sign match (first 4 letters)
    call_sign = re.search(r'^[k|w][a-z]{2,3}', simple_name)
    if call_sign:
        cs = call_sign.group(0)
        for simple_epg, original_id in epg_dict.items():
            if simple_epg.startswith(cs):
                return original_id
                
    return ""

def load_epg_database():
    """Returns a dictionary mapping {simplified_name: original_id}"""
    db = {}
    try:
        response = requests.get(EPG_DATA_URL, timeout=10)
        for line in response.text.splitlines():
            line = line.strip()
            if line and not line.startswith("--"):
                db[simplify(line)] = line
    except:
        pass
    return db

def check_link(url):
    headers = {'User-Agent': 'Mozilla/5.0 (VLC; Win64; x64)'}
    try:
        response = requests.get(url, headers=headers, timeout=7, stream=True, verify=False)
        return response.status_code < 400
    except:
        return False

def process_channel(name, url, genre, epg_db):
    is_active = check_link(url)
    
    # Grouping
    if "s.rocketdns.info:8080" in url:
        group = "Rocket"
    elif not is_active:
        group = "Offline"
    else:
        group = genre

    # Match against EPG database
    tvg_id = find_best_match(name, epg_db)
        
    return {
        "name": name, "url": url, "group": group, 
        "active": is_active, "tvg_id": tvg_id
    }

def main():
    print("Building EPG mapping database...")
    epg_db = load_epg_database()
    
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
            results = list(executor.map(lambda p: process_channel(*p, epg_db), channels_to_check))

        # Write Files
        m3u_output = [f'#EXTM3U x-tvg-url="{EPG_XML_URL}"']
        md_output = ["# 📺 Channel Status Dashboard", f"**Last Sync:** {datetime.now()} UTC\n", 
                     "| Status | Channel | Group | EPG Match |", "| :---: | :--- | :--- | :--- |"]

        for res in results:
            m3u_output.append(f'#EXTINF:-1 tvg-id="{res["tvg_id"]}" group-title="{res["group"]}",{res["name"]}')
            m3u_output.append(res["url"])
            
            icon = "✅" if res["active"] else "❌"
            md_output.append(f"| {icon} | {res['name']} | {res['group']} | `{res['tvg_id']}` |")

        with open(M3U_FILE, "w", encoding="utf-8") as f: f.write("\n".join(m3u_output))
        with open(MD_FILE, "w", encoding="utf-8") as f: f.write("\n".join(md_output))
        
        print(f"Success. Playlist updated at {datetime.now()}")

    except Exception as e:
        print(f"Critical Error: {e}")

if __name__ == "__main__":
    main()
