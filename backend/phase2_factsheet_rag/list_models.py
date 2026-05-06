import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv(dotenv_path=".env")
genai.configure(api_key=os.getenv("GEMINI_API_KEY_PHASE2_EMBEDDING_1"))

print("Available Embedding Models:")
for m in genai.list_models():
    if 'embedContent' in m.supported_generation_methods:
        print(f"- {m.name}")
