import os
import random
from typing import List, Dict, Any
from groq import Groq
import google.generativeai as genai
from pydantic import BaseModel
import json
from scraper import NormalizedReview
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))

# Configure Clients
groq_theme_client = Groq(api_key=os.getenv("GROQ_API_KEY_THEME_GENERATION"))

# Gemini Keys for rotation (Classification & Tagging)
gemini_keys = [
    os.getenv("GEMINI_API_KEY_PHASE1_CLASS_1"),
    os.getenv("GEMINI_API_KEY_PHASE1_CLASS_2")
]
gemini_keys = [k for k in gemini_keys if k] # Filter out None or empty

class Theme(BaseModel):
    theme_name: str
    short_description: str
    example_phrases: List[str]

def get_sample(reviews: List[NormalizedReview], sample_size: int = 200) -> List[NormalizedReview]:
    """Stage 2: Stratified sampling biased toward low ratings and long content."""
    if len(reviews) <= sample_size:
        return reviews
    
    # Stratify and bias (using reviews already cleansed by the pipeline)
    low_rated = [r for r in reviews if r.rating <= 3]
    high_rated = [r for r in reviews if r.rating > 3]
    
    target_low = int(sample_size * 0.7)
    target_high = sample_size - target_low
    
    sample = random.sample(low_rated, min(len(low_rated), target_low))
    sample += random.sample(high_rated, min(len(high_rated), target_high))
    
    return sample

def generate_themes(sample_reviews: List[NormalizedReview]) -> List[Theme]:
    """Stage 3: Theme Generation using Groq."""
    reviews_text = "\n".join([f"- {r.content}" for r in sample_reviews])
    
    prompt = f"""
    Analyze the following app reviews for a financial app (Groww) and identify 5-10 recurring themes.
    Each theme should be a specific user concern or topic (1-3 words).
    Return the result as a JSON array of objects with theme_name, short_description, and 3 example_phrases.
    
    Reviews:
    {reviews_text}
    """
    
    chat_completion = groq_theme_client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.3-70b-versatile",
        response_format={"type": "json_object"}
    )
    
    content = chat_completion.choices[0].message.content
    try:
        data = json.loads(content)
        
        # Smart Search: Look for common keys or the first list found in the JSON
        themes_data = []
        if isinstance(data, list):
            themes_data = data
        elif isinstance(data, dict):
            # Check common keys
            for key in ["themes", "recurring_themes", "categories", "analysis"]:
                if key in data and isinstance(data[key], list):
                    themes_data = data[key]
                    break
            # Fallback: Just find the first list in the dictionary
            if not themes_data:
                for val in data.values():
                    if isinstance(val, list):
                        themes_data = val
                        break
        
        valid_themes = []
        if isinstance(themes_data, list):
            for t in themes_data:
                if isinstance(t, dict):
                    valid_themes.append(Theme(
                        theme_name=t.get("theme_name", t.get("name", "General")),
                        short_description=t.get("short_description", t.get("description", "User feedback topic.")),
                        example_phrases=t.get("example_phrases", [])
                    ))
                elif isinstance(t, str):
                    valid_themes.append(Theme(theme_name=t, short_description=f"Reviews related to {t}.", example_phrases=[]))
        
        if not valid_themes:
            print(f"[Warning] No themes parsed. Raw content: {content[:200]}...")
            
        return valid_themes
    except Exception as e:
        print(f"Error parsing themes: {e}. Raw content: {content[:200]}...")
        return []

import concurrent.futures
import time
import urllib.request
import urllib.error

def classify_and_tag(reviews: List[NormalizedReview], themes: List[Theme]) -> List[Dict[str, Any]]:
    """Stage 4: Combined Classification and Sentiment Tagging in Parallel with Rate Smoothing."""
    results = []
    theme_names = [t.theme_name for t in themes]
    batch_size = 50
    
    # Split into batches
    batches = [reviews[i:i + batch_size] for i in range(0, len(reviews), batch_size)]
    
    def process_batch(batch, index):
        batch_text = "\n".join([f"ID:{r.review_id} | Content:{r.content[:300]}" for r in batch])
        prompt = f"""
        For each of the following reviews, perform two tasks:
        1. Classify it into exactly one of these themes: {', '.join(theme_names)}. If it doesn't fit, use 'Other'.
        2. Tag the sentiment as 'positive', 'neutral', or 'negative'.
        
        Return a JSON object where keys are the review IDs and values are objects with 'theme' and 'sentiment' keys.
        
        Reviews:
        {batch_text}
        """
        
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "response_mime_type": "application/json"
            }
        }
        
        max_retries = 5
        for attempt in range(max_retries):
            try:
                # Rotate key based on batch index and attempt
                key_index = (index + attempt) % len(gemini_keys)
                api_key = gemini_keys[key_index]
                
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
                req = urllib.request.Request(
                    url, 
                    data=json.dumps(payload).encode('utf-8'), 
                    headers={'Content-Type': 'application/json'}
                )
                
                with urllib.request.urlopen(req) as response:
                    res_body = response.read()
                    res_json = json.loads(res_body)
                    
                    content_text = res_json['candidates'][0]['content']['parts'][0]['text']
                    analysis_map = json.loads(content_text)
                    analysis_map = analysis_map.get("reviews", analysis_map)
                    
                    batch_results = []
                    for r in batch:
                        # Handle both string and int ID keys just in case
                        analysis = analysis_map.get(str(r.review_id), analysis_map.get(r.review_id, {"theme": "Other", "sentiment": "neutral"}))
                        batch_results.append({
                            **r.dict(),
                            "theme": analysis.get("theme", "Other"),
                            "sentiment": analysis.get("sentiment", "neutral")
                        })
                    
                    print(f"[ok] Batch {index} processed successfully (using Key {key_index + 1})")
                    return batch_results
            except Exception as e:
                print(f"Batch {index} attempt {attempt + 1} failed: {e}")
                time.sleep((2 ** attempt) + 3) # Exponential backoff + base delay
                
        print(f"Batch {index} completely failed after {max_retries} retries.")
        return [{**r.dict(), "theme": "Other", "sentiment": "neutral"} for r in batch]

    # Run batches in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(process_batch, b, i) for i, b in enumerate(batches)]
        for future in concurrent.futures.as_completed(futures):
            results.extend(future.result())
            
    return results
