import requests
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from thefuzz import fuzz, process

# --- Configuration ---
SOURCE_URL = "https://raw.githubusercontent.com/fleung49/star/refs/heads/main/OLY"
M3U_FILE = "playlist.m3u"
MD_FILE = "README.md"
MAX_WORKERS = 30 

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

MANUAL_MAP = {
    "u&gold": "Gold.uk", "u&w": "W.uk", "utv ireland": "UTV.uk",
    "virgin media one": "VirginMediaOne.ie", "virgin media two": "VirginMediaTwo.ie",
    "virgin media three": "VirginMediaThree.ie", "kcal": "KCAL-TV.us",
    "willow cricket": "Cricket.Dummy.us"
}

def find_best_epg_match(channel_name, databases):
    if not channel_name: return "", ""
    name_lower = channel_name.lower()
    
    for kw, m_id in MANUAL_MAP.items():
        if kw in name_lower: return m_id, ""

    call_sign_match = re.search(r'\b([kw][a-z]{3})\b', name_lower)
    if call_sign_match:
        call_sign = call_sign_match.group(1).upper()
        for e_id in databases.get("US_LOCALS", []):
            if e_id.upper().startswith(call_sign): return e_id, ""

    is_uk, is_ca = "(uk)" in name_lower or "(ire)" in name_lower, "(ca)" in name_lower
    is_west, is_us_local = "(west)" in name_lower, "los angeles" in name_lower or call_sign_match
    
    if is_uk: pool = databases.get("UK", [])
    elif is_ca: pool = databases.get("CA", [])
    elif is_us_local: pool = databases.get("US_LOCALS", []) + databases.get("US_CABLE", [])
    else: pool = databases.get("US_CABLE", []) + databases.get("DUMMY", [])
    
    clean_target = re.sub(r'\(.*?\)|-tv|hd|4k|[^a-z0-9\s]', '', name_lower).strip()
    match, score = process.extractOne(clean_target, pool, scorer=fuzz.token_set_ratio) if pool else (None, 0)
    
    if score >= 75:
        shift = "-3" if (is_west and ".west." not in match.lower()) else ""
        return match, shift

    dummy_match, dummy_score = process.extractOne(clean_target, databases.get("DUMMY", []), scorer=fuzz.token_set_ratio)
    if dummy_score >= 75: return dummy_match, ""
    
    return "", ""

def load_all_dbs():
    loaded = {}
    for key, url in EPG_DBS.items():
        try:
            r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
            loaded[key] = [l.strip() for l in r.text.splitlines() if l.strip() and not l.startswith("--")]
        except: loaded[key] = []
    return loaded

def check_link(url):
    try:
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5, stream=True)
        return r.status_code < 400
    except: return False

def process_channel(name, url, dbs):
    active = check_link(url)
    n_low, u_low = name.lower(), url.lower()
    
    # --- STATIC CATEGORIZATION WATERFALL ---
    # 1. Paid Services
    if "s.rocketdns.info" in u_low: group = "Rocket Service"
    elif "kstv.us" in u_low:
        if "(uk)" in n_low: group = "KSTV UK"
        elif "(ca)" in n_low: group = "KSTV Canada"
        else: group = "KSTV US"
    
    # 2. Branded FAST Providers
    elif "pluto.tv" in u_low: group = "Pluto TV"
    elif "roku.com" in u_low: group = "Roku Channel"
    elif "plex.tv" in u_low: group = "Plex TV"
    elif "tubi.io" in u_low or "tubi.video" in u_low: group = "Tubi TV"
    elif "localnow" in u_low or "amdvids.com" in u_low: group = "Local Now"
    
    # 3. Backend Infrastructure
    elif "amagi.tv" in u_low: group = "Backend: Amagi"
    elif "wurl.com" in u_low or "wurl.tv" in u_low: group = "Backend: Wurl"
    elif "cloudfront.net" in u_low: group = "Backend: Cloudfront"
    elif "syncbak.com" in u_low: group = "Backend: Syncbak"
    elif "uplynk.com" in u_low: group = "Backend: Uplynk"
    
    # 4. Specialized / Audio
    elif "ihrhls.com" in u_low: group = "Radio: iHeart"
    elif "stingray" in u_low: group = "Radio: Stingray"
    elif "vevo" in n_low or "vevo" in u_low: group = "Music: Vevo"
    elif "cablecast.tv" in u_low or "telvue.com" in u_low: group = "Local Gov/Public"
    elif "nextologies.com" in u_low or "univision" in u_low: group = "Spanish Services"
    elif "streamlock.net" in u_low: group = "Independent Streams"
    
    # 5. CATCH-ALL
    else: group = "Other Services"

    tvg_id, tvg_shift = find_best_epg_match(name, dbs)
    return {"name": name, "url": url, "group": group, "active": active, "tvg_id": tvg_id, "tvg_shift": tvg_shift}

def main():
    dbs = load_all_dbs()
    try:
        r = requests.get(SOURCE_URL)
        lines = r.text.splitlines()
        channels = []
        for l in lines:
            l = l.strip()
            # Ignore comments, empty lines, and specifically the #genre# tags
            if not l or l.startswith("#") or ",#genre#" in l: continue
            if "," in l:
                name, url = l.split(",", 1)
                channels.append((name.strip(), url.strip()))
        
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            results = list(executor.map(lambda p: process_channel(p[0], p[1], dbs), channels))
            
        with open(M3U_FILE, "w", encoding="utf-8") as f:
            f.write(f'#EXTM3U x-tvg-url="{",".join(XML_URLS)}"\n')
            for res in results:
                shift = f' tvg-shift="{res["tvg_shift"]}"' if res["tvg_shift"] else ""
                f.write(f'#EXTINF:-1 tvg-id="{res["tvg_id"]}"{shift} group-title="{res["group"]}",{res["name"]}\n')
                f.write(f'{res["url"]}\n')

        with open(MD_FILE, "w", encoding="utf-8") as f:
            f.write(f"# 📺 Playlist Status Update: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
            f.write("| Status | Channel | Provider Group | EPG Match |\n| :---: | :--- | :--- | :--- |\n")
            for res in results:
                icon = "✅" if res["active"] else "❌"
                f.write(f"| {icon} | {res['name']} | {res['group']} | `{res['tvg_id']}` |\n")
    except Exception as e: print(f"Error: {e}")

if __name__ == "__main__":
    main()
