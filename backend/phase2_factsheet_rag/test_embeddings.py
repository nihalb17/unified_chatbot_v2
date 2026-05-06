import os
import sys
from dotenv import load_dotenv

# Add the phase2 directory to path so we can import embedder
sys.path.append(os.path.join(os.getcwd(), "backend/phase2_factsheet_rag"))

from embedder import embed_texts

def test_gemini_embeddings():
    load_dotenv()
    print("Testing Gemini Embedding Rotation...")
    test_texts = ["What is the NAV of Axis Bluechip Fund?", "How much is the exit load?"]
    
    try:
        embeddings = embed_texts(test_texts)
        print(f"Successfully generated {len(embeddings)} embeddings.")
        print(f"Dimensions: {len(embeddings[0]) if embeddings else 'N/A'}")
        if len(embeddings[0]) == 768:
            print("SUCCESS: Dimensions match Gemini text-embedding-004 (768).")
        else:
            print(f"WARNING: Dimensions are {len(embeddings[0])}, expected 768.")
    except Exception as e:
        print(f"FAILED: {e}")

if __name__ == "__main__":
    test_gemini_embeddings()
