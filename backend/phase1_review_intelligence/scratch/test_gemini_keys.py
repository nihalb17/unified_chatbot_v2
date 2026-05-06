import urllib.request
import json
import os
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../../.env"))

keys = [
    os.getenv("GEMINI_API_KEY_PHASE1_CLASS_1"),
    os.getenv("GEMINI_API_KEY_PHASE1_CLASS_2")
]
model = "gemini-2.5-flash"

payload = {
    "contents": [{"parts": [{"text": "Say hello"}]}]
}

for i, api_key in enumerate(keys):
    if not api_key:
        print(f"Key {i+1} is missing")
        continue
        
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    req = urllib.request.Request(
        url, 
        data=json.dumps(payload).encode('utf-8'), 
        headers={'Content-Type': 'application/json'}
    )

    try:
        with urllib.request.urlopen(req) as response:
            res_body = response.read()
            print(f"Success with Key {i+1}: {res_body[:50]}...")
    except Exception as e:
        print(f"Failed with Key {i+1}: {e}")
