import requests
import re
import urllib3
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# Suppress SSL warnings (for links with expired certs)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configuration
SOURCE_URL = "https://raw.githubusercontent.com/fleung49/star/refs/heads/main/OLY"
EPG_XML_URL = "https://epgshare01.online/epgshare01/epg_ripper_ALL_SOURCES1.xml.gz"
EPG_DATA_URL = "https://raw.githubusercontent.com/fleung49/star/main/epg_ripper_ALL_SOURCES1.txt"

M3U_FILE = "playlist.m3u"
MD_FILE = "README.md"
MAX_WORKERS = 25 

def clean_text(text):
    """
    Standardizes names by removing dots, dashes, and spaces.
    Example: 'A.and.E.HD.us2' -> 'aandehd'
             'A&E HD' -> 'aandehd'
    """
    if not text: return ""
    text = text.lower()
    # Remove common EPG suffixes like .us2, .ca2, .uk
    text = re.sub(r'\.[a-z]{2,3}\d?$', '', text)
    # Remove everything except letters and numbers
    return re.sub(r'[^a-z0-9]', '', text)

def find_epg_match(channel_name, epg_list):
    """
    Attempts to find the EPG ID.
    1. Looks for Call Sign match (e.g. KCBS)
    2. Looks for simplified string match
    """
    simple_name = clean_text(channel_name)
    
    # Extract Call Sign (first 4 characters starting with K or W)
    call_sign_match = re.search(r'^[k|w][a-z]{2,3}', simple_name)
    call_sign = call_sign_match.group(0) if call_sign_match else None

    for epg_id in epg_list:
        simple_epg = clean_text(epg_id)
        
        # Match by Call Sign (e.g. KCBS match KCBS.us2)
        if call_sign and simple_epg.startswith(call_sign):
            return epg_id
            
        # Match by full simplified name
        if simple_name in simple_epg or simple_epg in simple_name:
            return epg_id
            
    return ""

def load_epg_database():
    """Downloads the list of EPG IDs from your repo."""
    try:
        response = requests.get(EPG_DATA_URL, timeout=10)
        return [line.strip() for line in response.text.splitlines() if line.strip() and not line.startswith("--")]
    except:
        return []

def check_link(url):
    """Checks link status; verify=False allows expired certs to stay 'Online'."""
    headers = {'User-Agent': 'Mozilla/5.0 (VLC; Win64; x64)'}
    try:
        response = requests.get(url, headers=headers, timeout=7, stream=True, verify=False)
        return response.status_code < 400
    except:
        return False

def process_channel(name, url, genre, epg_list):
    is_active = check_link(url)
    
    # Rocket Grouping
    if "s.rocketdns.info:8080" in url:
        group = "Rocket"
    elif not is_active:
        group = "Offline"
    else:
        group = genre

    # Map the EPG ID
    tvg_id = find_epg_match(name, epg_list)
        
    return {
        "name": name, "url": url, "group": group, 
        "active": is_active, "tvg_id": tvg_id
    }

def main():
    print("Building EPG ID database...")
    epg_list = load_epg_database()
    
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

        print(f"Checking {len(channels_to_check)} channels...")
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            results = list(executor.map(lambda p: process_channel(*p, epg_list), channels_to_check))

        # Output M3U
        m3u_lines = [f'#EXTM3U x-tvg-url="{EPG_XML_URL}"']
        for res in results:
            m3u_lines.append(f'#EXTINF:-1 tvg-id="{res["tvg_id"]}" group-title="{res["group"]}",{res["name"]}')
            m3u_lines.append(res["url"])
            
        # Output README
        md_lines = ["# 📺 Channel Status Dashboard", f"**Last Update:** {datetime.now()} UTC\n", 
                    "| Status | Channel | Group | EPG ID |", "| :---: | :--- | :--- | :--- |"]
        for res in results:
            icon = "✅" if res["active"] else "❌"
            md_lines.append(f"| {icon} | {res['name']} | {res['group']} | `{res['tvg_id']}` |")

        with open(M3U_FILE, "w", encoding="utf-8") as f: f.write("\n".join(m3u_lines))
        with open(MD_FILE, "w", encoding="utf-8") as f: f.write("\n".join(md_lines))
        print("Success.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
