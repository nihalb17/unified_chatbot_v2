import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv(dotenv_path=".env")
genai.configure(api_key=os.getenv("GEMINI_API_KEY_PHASE2_EMBEDDING_1"))

model = "models/gemini-embedding-2"
print(f"\nModel: {model}")
try:
    res = genai.embed_content(model=model, content="test", task_type="retrieval_query")
    print(f"Dimensions: {len(res['embedding'])}")
except Exception as e:
    print(f"Error: {e}")
