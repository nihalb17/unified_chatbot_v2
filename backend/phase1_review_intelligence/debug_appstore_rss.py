import requests
import json

def test_rss():
    app_id = "1404871703"
    region = "in"
    url = f"https://itunes.apple.com/{region}/rss/customerreviews/id={app_id}/json"
    print(f"Fetching RSS from {url}...")
    
    try:
        response = requests.get(url)
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            entries = data.get('feed', {}).get('entry', [])
            print(f"Successfully fetched {len(entries)} reviews via RSS.")
            if entries:
                print("Sample review:", entries[0].get('content', {}).get('label', '')[:100])
        else:
            print(f"Response: {response.text[:200]}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_rss()
