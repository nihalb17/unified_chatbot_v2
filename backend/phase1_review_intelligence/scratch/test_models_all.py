import urllib.request
import json
import os
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../../.env"))

api_key = os.getenv("GEMINI_API_KEY_PHASE1_CLASS_1")
models = ["gemini-1.5-flash", "gemini-2.0-flash", "gemini-2.0-flash-exp", "gemini-2.5-flash"]

payload = {
    "contents": [{"parts": [{"text": "Say hello"}]}]
}

for model in models:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    req = urllib.request.Request(
        url, 
        data=json.dumps(payload).encode('utf-8'), 
        headers={'Content-Type': 'application/json'}
    )

    try:
        with urllib.request.urlopen(req) as response:
            res_body = response.read()
            print(f"Success with {model}")
    except Exception as e:
        print(f"Failed with {model}: {e}")
