import os
import json
from datetime import datetime
from typing import List, Dict, Any
from analyzer import Theme
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))

def aggregate_results(classified_reviews: List[Dict[str, Any]], themes: List[Theme]) -> Dict[str, Any]:
    """Stage 5: Aggregate results and generate actionable items in batch."""
    
    theme_stats = []
    total_processed = len(classified_reviews)
    play_count = sum(1 for r in classified_reviews if r['source'] == 'playstore')
    app_count = sum(1 for r in classified_reviews if r['source'] == 'appstore')
    
    # 1. Collect data for each theme
    batch_data = []
    for theme in themes:
        theme_reviews = [r for r in classified_reviews if r['theme'] == theme.theme_name]
        if not theme_reviews: continue
            
        sentiments = [r['sentiment'] for r in theme_reviews]
        dominant_sentiment = max(set(sentiments), key=sentiments.count)
        sorted_quotes = sorted(theme_reviews, key=lambda x: len(x['content']), reverse=True)
        representative_quotes = [{"text": q['content'], "source": q['source']} for q in sorted_quotes[:3]]
        
        theme_stats.append({
            "theme_name": theme.theme_name,
            "short_description": theme.short_description,
            "sentiment": dominant_sentiment,
            "total_mentions": len(theme_reviews),
            "playstore_mentions": sum(1 for r in theme_reviews if r['source'] == 'playstore'),
            "appstore_mentions": sum(1 for r in theme_reviews if r['source'] == 'appstore'),
            "representative_quotes": representative_quotes,
            "actionable_item": f"Pending analysis for {theme.theme_name}"
        })
        batch_data.append({"name": theme.theme_name, "quotes": representative_quotes})

    # 2. Assign actionable items using Gemini
    import urllib.request
    api_key = os.getenv("GEMINI_API_KEY_PHASE1_CLASS_1")
    if api_key and theme_stats:
        print("[Stage 5/5] Generating intelligent actionable items for themes...")
        
        # Build prompt
        prompt = "You are a senior product manager. Based on the following themes and their representative user reviews, generate a highly specific, single-sentence actionable item for the product/engineering team to address the core issue/praise. Return a JSON object mapping the theme name exactly to the actionable item string.\n\n"
        for stats in theme_stats:
            prompt += f"Theme: {stats['theme_name']}\nReviews:\n"
            for q in stats['representative_quotes']:
                prompt += f"- {q['text']}\n"
            prompt += "\n"
            
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"response_mime_type": "application/json"}
        }
        
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
        req = urllib.request.Request(
            url, 
            data=json.dumps(payload).encode('utf-8'), 
            headers={'Content-Type': 'application/json'}
        )
        
        try:
            with urllib.request.urlopen(req) as response:
                res_body = response.read()
                res_json = json.loads(res_body)
                content_text = res_json['candidates'][0]['content']['parts'][0]['text']
                actionable_items = json.loads(content_text)
                
                for stats in theme_stats:
                    if stats['theme_name'] in actionable_items:
                        stats['actionable_item'] = actionable_items[stats['theme_name']]
        except Exception as e:
            print(f"Failed to generate actionable items: {e}")
            for stats in theme_stats:
                stats["actionable_item"] = f"Review recent feedback related to '{stats['theme_name']}' to identify and resolve root causes."
    else:
        for stats in theme_stats:
            stats["actionable_item"] = f"Review recent feedback related to '{stats['theme_name']}' to identify and resolve root causes."

    return {
        "refresh_metadata": {
            "timestamp": datetime.now().isoformat(),
            "total_reviews_processed": total_processed,
            "source_breakdown": {"playstore": play_count, "appstore": app_count}
        },
        "themes": theme_stats
    }

def save_kb(kb_data: Dict[str, Any]):
    """Persists the knowledge base to a JSON file."""
    data_dir = os.path.join(os.path.dirname(__file__), "../data")
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
        
    file_path = os.path.join(data_dir, "themes_kb.json")
    with open(file_path, "w") as f:
        json.dump(kb_data, f, indent=2)
    print(f"Knowledge base saved to {file_path}")
