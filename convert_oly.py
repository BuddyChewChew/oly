import requests
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from thefuzz import fuzz, process

# --- Configuration ---
SOURCE_URL = "https://raw.githubusercontent.com/fleung49/star/refs/heads/main/OLY"

EPG_DBS = {
    "US_LOCALS": "https://epgshare01.online/epgshare01/epg_ripper_US_LOCALS1.txt",
    "US_CABLE": "https://epgshare01.online/epgshare01/epg_ripper_US2.txt",
    "UK": "https://epgshare01.online/epgshare01/epg_ripper_UK1.txt",
    "CA": "https://epgshare01.online/epgshare01/epg_ripper_CA2.txt",
    "DUMMY": "https://epgshare01.online/epgshare01/epg_ripper_DUMMY_CHANNELS.txt"
}

XML_URLS = [
    "https://epgshare01.online/epgshare01/epg_ripper_US2.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_US_LOCALS1.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_UK1.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_CA2.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_DUMMY_CHANNELS.xml.gz"
]

M3U_FILE = "playlist.m3u"
MD_FILE = "README.md"
MAX_WORKERS = 30 

def find_best_epg_match(channel_name, databases):
    if not channel_name: return "", ""
    name_lower = channel_name.lower()
    
    # 1. CALL SIGN HARVESTER (The "WNAB" Fix)
    # This looks for a 4-letter word starting with K or W
    call_sign_match = re.search(r'\b([kw][a-z]{3})\b', name_lower)
    if call_sign_match:
        call_sign = call_sign_match.group(1).upper()
        # Look specifically in US_LOCALS for any ID starting with WNAB
        for e_id in databases.get("US_LOCALS", []):
            if e_id.upper().startswith(call_sign):
                return e_id, ""

    # 2. Regional Analysis
    is_uk = "(uk)" in name_lower or "(ire)" in name_lower
    is_ca = "(ca)" in name_lower and "los angeles" not in name_lower
    is_west = "(west)" in name_lower
    is_us_local = "los angeles" in name_lower or call_sign_match

    # 3. Pool Selection
    if is_uk:
        pool = databases.get("UK", [])
    elif is_ca:
        pool = databases.get("CA", [])
    elif is_us_local:
        pool = databases.get("US_LOCALS", []) + databases.get("US_CABLE", [])
    else:
        pool = databases.get("US_CABLE", []) + databases.get("DUMMY", [])

    # 4. Fuzzy Matching
    clean_target = re.sub(r'\(.*?\)|-tv|hd|4k|[^a-z0-9\s]', '', name_lower).strip()
    match, score = process.extractOne(clean_target, pool, scorer=fuzz.token_set_ratio) if pool else (None, 0)
    
    if score >= 75:
        shift = "-3" if (is_west and ".west." not in match.lower()) else ""
        return match, shift

    # 5. Dummy Fallback
    dummy_match, dummy_score = process.extractOne(clean_target, databases.get("DUMMY", []), scorer=fuzz.token_set_ratio)
    if dummy_score >= 75:
        return dummy_match, ""

    return "", ""

# ... (rest of the script remains same as the multi-source version)

def load_all_dbs():
    loaded = {}
    headers = {'User-Agent': 'Mozilla/5.0'}
    for key, url in EPG_DBS.items():
        try:
            r = requests.get(url, headers=headers, timeout=15)
            r.raise_for_status()
            loaded[key] = [l.strip() for l in r.text.splitlines() if l.strip() and not l.startswith("--")]
        except:
            loaded[key] = []
    return loaded

def check_link(url):
    try:
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5, stream=True)
        return r.status_code < 400
    except:
        return False

def process_channel(name, url, genre, dbs):
    active = check_link(url)
    group = "Rocket" if "s.rocketdns.info:8080" in url else ("Offline" if not active else genre)
    tvg_id, tvg_shift = find_best_epg_match(name, dbs)
    return {"name": name, "url": url, "group": group, "active": active, "tvg_id": tvg_id, "tvg_shift": tvg_shift}

def main():
    dbs = load_all_dbs()
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
            results = list(executor.map(lambda p: process_channel(*p, dbs), channels))
        with open(M3U_FILE, "w", encoding="utf-8") as f:
            f.write(f'#EXTM3U x-tvg-url="{",".join(XML_URLS)}"\n')
            for res in results:
                shift = f' tvg-shift="{res["tvg_shift"]}"' if res["tvg_shift"] else ""
                f.write(f'#EXTINF:-1 tvg-id="{res["tvg_id"]}"{shift} group-title="{res["group"]}",{res["name"]}\n')
                f.write(f'{res["url"]}\n')
        with open(MD_FILE, "w", encoding="utf-8") as f:
            f.write("# 📺 Call-Sign Matched Dashboard\n\n| Status | Channel | Group | EPG Match |\n| :---: | :--- | :--- | :--- |\n")
            for res in results:
                icon = "✅" if res["active"] else "❌"
                f.write(f"| {icon} | {res['name']} | {res['group']} | `{res['tvg_id']}` |\n")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
