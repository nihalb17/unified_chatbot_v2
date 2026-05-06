import sys
import os
import json
sys.path.append(r"c:\Users\nihal\Downloads\NL_Projects\Capstone_Project_v2\backend\phase2_factsheet_rag")
from agent import run_faq_agent
from dotenv import load_dotenv

# Load environment variables (GROQ_API_KEY_FAQ_AGENT)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../../.env"))

query = "What is the NAV of Axis Liquid?"
print(f"Testing query: {query}")

result = run_faq_agent(query)

print("\n--- Agent Result ---")
print(f"Type: {result['type']}")
# Replace the rupee symbol for printing
clean_text = result['text'].replace('₹', 'Rs.')
print(f"Text: {clean_text}")
print("Links:")
for link in result.get('links', []):
    print(f"  - {link['label']}: {link['url']}")

if "3087.814" in result['text']:
    print("\nSUCCESS: NAV found in response.")
else:
    print("\nFAILURE: NAV not found in response.")
