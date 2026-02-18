import requests
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

SOURCE_URL = "https://raw.githubusercontent.com/fleung49/star/refs/heads/main/OLY"
M3U_FILE = "playlist.m3u"
MD_FILE = "README.md"
MAX_WORKERS = 20 

def check_link(url):
    """Checks link status using a player-like User-Agent."""
    # Custom headers to look like a real IPTV player
    headers = {
        'User-Agent': 'Mozilla/5.0 (VLC; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }
    try:
        # Using stream=True with a GET request is more reliable than HEAD for many IPTV servers
        response = requests.get(url, headers=headers, timeout=7, stream=True, allow_redirects=True)
        # If we get a 200 (OK) or similar, it's live
        return response.status_code < 400
    except:
        return False

def process_channel(name, url, genre):
    """Determines the group based on URL content and live status."""
    is_active = check_link(url)
    
    # Priority 1: RocketDNS Group
    if "s.rocketdns.info:8080" in url:
        group = "Rocket"
    # Priority 2: Offline Group (if non-rocket and dead)
    elif not is_active:
        group = "Offline"
    # Priority 3: Original Genre (if live)
    else:
        group = genre
        
    return {
        "name": name,
        "url": url,
        "group": group,
        "active": is_active,
        "original_genre": genre
    }

def main():
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
                current_genre = line.split(",#genre#")[0].strip()
                continue
            if "," in line:
                parts = line.split(",", 1)
                name = parts[0].strip()
                url = parts[1].strip()
                channels_to_check.append((name, url, current_genre))

        print(f"Checking {len(channels_to_check)} channels...")
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            results = list(executor.map(lambda p: process_channel(*p), channels_to_check))

        m3u_lines = ["#EXTM3U"]
        md_lines = [
            "# 📺 Channel Status Dashboard",
            f"**Last Updated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC\n",
            "| Status | Channel Name | Final Group | Original Category |",
            "| :---: | :--- | :--- | :--- |"
        ]

        for res in results:
            m3u_lines.append(f'#EXTINF:-1 group-title="{res["group"]}",{res["name"]}')
            m3u_lines.append(res["url"])
            
            icon = "✅" if res["active"] else "❌"
            md_lines.append(f"| {icon} | {res['name']} | **{res['group']}** | {res['original_genre']} |")

        with open(M3U_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(m3u_lines))
        with open(MD_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(md_lines))
            
        print(f"Update finished. {len(results)} channels processed.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
