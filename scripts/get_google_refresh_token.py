"""
Helper script to generate a new GOOGLE_REFRESH_TOKEN for Google Workspace integration.

Usage:
    python scripts/get_google_refresh_token.py
"""

import os
import sys
from google_auth_oauthlib.flow import InstalledAppFlow
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../.env"))

CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()

if not CLIENT_ID or not CLIENT_SECRET:
    print("\n[Error] GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set in your .env file.")
    sys.exit(1)

client_config = {
    "installed": {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost"]
    }
}

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/drive.file",
]

print("\n[+] Launching local browser for Google Authorization...")
print("[+] Sign in to the Google account managing your Calendar / Gmail.")

# Try port 8080, then 8085, then 0 (auto-select available free port)
ports_to_try = [8085, 8090, 8099, 0]
creds = None

for p in ports_to_try:
    try:
        flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)
        creds = flow.run_local_server(port=p, prompt="consent", access_type="offline")
        if creds:
            break
    except OSError as os_err:
        if "10048" in str(os_err) or "address already in use" in str(os_err).lower():
            continue
        raise os_err
    except Exception as e:
        print(f"\n[Error] Authorization failed: {e}")
        sys.exit(1)

if creds and creds.refresh_token:
    print("\n" + "=" * 70)
    print("SUCCESS! Generated your new GOOGLE_REFRESH_TOKEN:")
    print("=" * 70)
    print(creds.refresh_token)
    print("=" * 70 + "\n")
    print("Next steps:")
    print("1. Copy this new GOOGLE_REFRESH_TOKEN into your local .env file.")
    print("2. Copy this new GOOGLE_REFRESH_TOKEN into your Render Environment Variables.")
else:
    print("\n[Error] Could not obtain a refresh token. Make sure you approved access in the browser.")
