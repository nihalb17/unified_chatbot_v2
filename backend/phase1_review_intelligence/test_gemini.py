import os
from dotenv import load_dotenv
import urllib.request
import json

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))
key = os.getenv("GEMINI_API_KEY_PHASE1_CLASS_1")
print(f"Key loaded: {key}")

url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={key}"
payload = {"contents": [{"parts": [{"text": "Hello"}]}]}
req = urllib.request.Request(
    url, 
    data=json.dumps(payload).encode('utf-8'), 
    headers={'Content-Type': 'application/json'}
)

try:
    with urllib.request.urlopen(req) as response:
        print("Success:", response.status)
except Exception as e:
    print("Error:", e)
    if hasattr(e, 'read'):
        print(e.read())
