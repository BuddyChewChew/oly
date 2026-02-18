import requests

# Source URL for the OLY file
SOURCE_URL = "https://raw.githubusercontent.com/fleung49/star/refs/heads/main/OLY"
OUTPUT_FILE = "playlist.m3u"

def check_link(url):
    """
    Checks if a URL is active with a 5-second timeout.
    Returns True if the link is reachable.
    """
    try:
        # Use a HEAD request for speed, following redirects if necessary
        response = requests.head(url, timeout=5, allow_redirects=True)
        return response.status_code < 400
    except:
        return False

def main():
    try:
        # Fetch the OLY file content
        response = requests.get(SOURCE_URL)
        response.raise_for_status()
        lines = response.text.splitlines()

        m3u_content = ["#EXTM3U"]

        for line in lines:
            line = line.strip()
            # Skip empty lines or genre markers in the source
            if not line or ",#genre#" in line:
                continue
            
            # The OLY file uses Name,URL format [cite: 1]
            if "," in line:
                parts = line.split(",")
                name = parts[0].strip()
                url = parts[1].strip()
                
                # Check status and assign to "Live" or "Offline" group
                is_active = check_link(url)
                group = "Live" if is_active else "Offline"
                
                m3u_content.append(f'#EXTINF:-1 group-title="{group}",{name}')
                m3u_content.append(url)

        # Write the final .m3u file
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(m3u_content))
            
        print(f"Playlist updated with {len(m3u_content)//2} channels.")

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
