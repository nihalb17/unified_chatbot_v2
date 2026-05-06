import os
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from pydantic import BaseModel, Field
from google_play_scraper import reviews, Sort
from app_store_scraper import AppStore
import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))

class NormalizedReview(BaseModel):
    review_id: str
    source: str
    date: datetime
    rating: int
    title: Optional[str] = None
    content: str

def fetch_play_store_reviews(app_id: str, region: str, count: int = 500) -> List[NormalizedReview]:
    """Fetches exactly 'count' latest reviews from Google Play Store."""
    all_reviews = []
    
    # We fetch in batches of 100 until we hit the count
    continuation_token = None
    while len(all_reviews) < count:
        result, continuation_token = reviews(
            app_id,
            lang='en',
            country=region,
            sort=Sort.NEWEST,
            count=100,
            continuation_token=continuation_token
        )
        
        for r in result:
            all_reviews.append(NormalizedReview(
                review_id=r['reviewId'],
                source='playstore',
                date=r['at'],
                rating=r['score'],
                title=None,
                content=r['content']
            ))
            if len(all_reviews) >= count:
                break
            
        if not continuation_token or len(all_reviews) >= count:
            break
            
    return all_reviews[:count]

def fetch_app_store_reviews(app_id: str, region: str, count: int = 500) -> List[NormalizedReview]:
    """Fetches up to 'count' latest reviews from Apple App Store using RSS feed."""
    all_reviews = []
    
    # Apple RSS feed provides up to 10 pages of 50 reviews each (total 500)
    for page in range(1, 11):
        url = f"https://itunes.apple.com/{region}/rss/customerreviews/page={page}/id={app_id}/sortby=mostrecent/json"
        try:
            response = requests.get(url)
            if response.status_code != 200:
                break
                
            data = response.json()
            entries = data.get('feed', {}).get('entry', [])
            
            if not entries:
                break
                
            if isinstance(entries, dict):
                entries = [entries]
                
            for r in entries:
                if 'im:name' in r:
                    continue
                    
                date_str = r.get('updated', {}).get('label', '')
                try:
                    review_date = datetime.fromisoformat(date_str.replace('Z', '+00:00')).replace(tzinfo=None)
                except:
                    review_date = datetime.now()

                all_reviews.append(NormalizedReview(
                    review_id=r.get('id', {}).get('label', 'unknown'),
                    source='appstore',
                    date=review_date,
                    rating=int(r.get('im:rating', {}).get('label', 0)),
                    title=r.get('title', {}).get('label', ''),
                    content=r.get('content', {}).get('label', '')
                ))
                
                if len(all_reviews) >= count:
                    return all_reviews
        except Exception as e:
            print(f"Error fetching page {page}: {e}")
            break
            
    return all_reviews[:count]

def get_combined_reviews(count_per_store: int = 500) -> List[NormalizedReview]:
    """Orchestrates the fetching and merging of reviews from both stores."""
    play_id = os.getenv("PLAYSTORE_APP_ID", "com.nextbillion.groww")
    app_id = os.getenv("APPSTORE_APP_ID", "1404871703")
    region = os.getenv("APP_STORE_REGION", "in")
    
    print(f"Fetching latest {count_per_store} reviews from each store...")
    
    play_reviews = fetch_play_store_reviews(play_id, region, count_per_store)
    app_reviews = fetch_app_store_reviews(app_id, region, count_per_store)
    
    combined = play_reviews + app_reviews
    print(f"Fetched {len(play_reviews)} Play Store reviews and {len(app_reviews)} App Store reviews.")
    
    return combined

if __name__ == "__main__":
    reviews_list = get_combined_reviews()
    print(f"Total reviews fetched: {len(reviews_list)}")
