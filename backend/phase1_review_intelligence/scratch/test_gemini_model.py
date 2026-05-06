import urllib.request
import json
import os
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../../.env"))

api_key = os.getenv("GEMINI_API_KEY_PHASE1_CLASS_1")
model = "gemini-1.5-flash" # Testing with a known model

payload = {
    "contents": [{"parts": [{"text": "Say hello"}]}]
}

url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
req = urllib.request.Request(
    url, 
    data=json.dumps(payload).encode('utf-8'), 
    headers={'Content-Type': 'application/json'}
)

try:
    with urllib.request.urlopen(req) as response:
        res_body = response.read()
        print(f"Success with {model}: {res_body[:100]}...")
except Exception as e:
    print(f"Failed with {model}: {e}")

# Now test the original one
model2 = "gemini-2.5-flash"
url2 = f"https://generativelanguage.googleapis.com/v1beta/models/{model2}:generateContent?key={api_key}"
req2 = urllib.request.Request(
    url2, 
    data=json.dumps(payload).encode('utf-8'), 
    headers={'Content-Type': 'application/json'}
)

try:
    with urllib.request.urlopen(req2) as response:
        res_body = response.read()
        print(f"Success with {model2}: {res_body[:100]}...")
except Exception as e:
    print(f"Failed with {model2}: {e}")
