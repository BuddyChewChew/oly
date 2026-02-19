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
    if not channel_name or not epg_list:
        return "", ""
    
    name_lower = channel_name.lower()
    shift = ""
    
    # Identify Region/Shift
    is_uk = "(uk)" in name_lower or "(ire)" in name_lower
    is_west = "(west)" in name_lower
    is_us_ca = "(ca)" in name_lower or "(east)" in name_lower or "(la)" in name_lower or is_west
    
    # 1. CALL SIGN EXTRACTION
    call_sign_match = re.search(r'\b([kw][a-z]{2,3})\b', name_lower)
    call_sign = call_sign_match.group(1) if call_sign_match else None

    # 2. FILTERED POOL
    regional_pool = []
    if is_uk:
        regional_pool = [e for e in epg_list if e.lower().endswith(('.uk', '.ie', '.uk2'))]
    elif is_us_ca or call_sign:
        regional_pool = [e for e in epg_list if '.us' in e.lower() or '.ca' in e.lower()]
    
    search_pool = regional_pool if regional_pool else epg_list

    # 3. DIRECT SEARCH (Try exact first)
    clean_target = re.sub(r'\(.*?\)|-tv|hd|4k|[^a-z0-9\s]', '', name_lower).strip()
    
    match, score = process.extractOne(clean_target, search_pool, scorer=fuzz.token_set_ratio)
    
    # 4. FALLBACK & TIMESHIFT LOGIC
    # If we matched a 'West' channel to a generic ID, apply -3 shift
    if score >= 80:
        if is_west and ".west." not in match.lower():
            shift = "-3"
        return match, shift

    return "", ""

def load_epg_database():
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(EPG_DATA_URL, headers=headers, timeout=20)
        r.raise_for_status()
        return [l.strip() for l in r.text.splitlines() if l.strip() and not l.startswith("--")]
    except Exception as e:
        print(f"Error loading EPG: {e}")
        return []

def check_link(url):
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        r = requests.get(url, headers=headers, timeout=5, stream=True)
        return r.status_code < 400
    except:
        return False

def process_channel(name, url, genre, epg_list):
    active = check_link(url)
    
    # Grouping Logic
    if "s.rocketdns.info:8080" in url:
        group = "Rocket"
    elif not active:
        group = "Offline"
    else:
        group = genre

    tvg_id, tvg_shift = find_best_epg_match(name, epg_list)
    return {
        "name": name, "url": url, "group": group, "active": active, 
        "tvg_id": tvg_id, "tvg_shift": tvg_shift
    }

def main():
    print(f"Sync started: {datetime.now().strftime('%H:%M:%S')}")
    epg_list = load_epg_database()
    
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

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            results = list(executor.map(lambda p: process_channel(*p, epg_list), channels))

        # Output Playlist with tvg-shift support
        with open(M3U_FILE, "w", encoding="utf-8") as f:
            f.write(f'#EXTM3U x-tvg-url="{EPG_XML_URL}"\n')
            for res in results:
                shift_tag = f' tvg-shift="{res["tvg_shift"]}"' if res["tvg_shift"] else ""
                f.write(f'#EXTINF:-1 tvg-id="{res["tvg_id"]}"{shift_tag} group-title="{res["group"]}",{res["name"]}\n')
                f.write(f'{res["url"]}\n')

        # Output README
        with open(MD_FILE, "w", encoding="utf-8") as f:
            f.write("# 📺 Channel Status Dashboard\n\n| Status | Channel | Group | EPG Match | Shift |\n| :---: | :--- | :--- | :--- | :---: |\n")
            for res in results:
                icon = "✅" if res["active"] else "❌"
                f.write(f"| {icon} | {res['name']} | {res['group']} | `{res['tvg_id']}` | {res['tvg_shift']} |\n")
        
        print("Success.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
