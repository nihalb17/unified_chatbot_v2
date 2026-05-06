import sys
import os
sys.path.append(r"c:\Users\nihal\Downloads\NL_Projects\Capstone_Project_v2\backend\phase2_factsheet_rag")
from retriever import retrieve_chunks

query = "Axis Liquid nav"
chunks = retrieve_chunks(query, n_results=10)

print(f"Query: {query}")
print(f"Retrieved {len(chunks)} chunks:")
for c in chunks:
    # Print without the rupee symbol to avoid encoding issues
    clean_text = c['text'].replace('₹', 'Rs.')
    print(f"--- ID: {c['id']} (Distance: {c.get('distance')}) ---")
    print(f"Text: {clean_text}")
