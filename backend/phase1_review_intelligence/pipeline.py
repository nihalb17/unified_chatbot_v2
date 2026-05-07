from scraper import get_combined_reviews
from analyzer import get_sample, generate_themes, classify_and_tag
from aggregator import aggregate_results, save_kb

def run_pipeline():
    """Executes the full Phase 1 pipeline."""
    print("Starting Review Intelligence Pipeline...")
    
    # [Stage 1/5] Fetch
    all_reviews = get_combined_reviews(count_per_store=175)
    if not all_reviews:
        print("[Error] No reviews found. Exiting.")
        return
        
    # [Stage 1.5] Cleanse (Length & PII)
    # Filter for meaningful content (>= 5 words) and ensure no PII
    initial_count = len(all_reviews)
    all_reviews = [r for r in all_reviews if len(r.content.split()) >= 5]
    
    play_clean = sum(1 for r in all_reviews if r.source == 'playstore')
    app_clean = sum(1 for r in all_reviews if r.source == 'appstore')
    
    print(f"[Stage 1.5] Cleansed: {initial_count} -> {len(all_reviews)} (Dropped {initial_count - len(all_reviews)})")
    print(f"            Breakdown: {play_clean} Play Store | {app_clean} App Store")
    
    # [Stage 2/5] Sample
    sample = get_sample(all_reviews)
    print(f"[Stage 2/5] Sampled {len(sample)} reviews for theme discovery.")
    
    # [Stage 3/5] Theme Generation
    print("[Stage 3/5] Generating themes via AI...")
    themes = generate_themes(sample)
    theme_list = ", ".join([t.theme_name for t in themes])
    print(f"[Stage 3/5] Discovered {len(themes)} themes: {theme_list}")
    
    # [Stage 4/5] Classification & Tagging
    print(f"[Stage 4/5] Classifying and tagging {len(cleansed_reviews)} reviews (this may take a minute)...")
    classified_data = classify_and_tag(all_reviews, themes)
    
    # [Stage 5/5] Aggregate & Persist
    print("[Stage 5/5] Aggregating results and generating actionable items...")
    kb_data = aggregate_results(classified_data, themes)
    save_kb(kb_data)
    
    print("Pipeline completed successfully!")
    return kb_data

if __name__ == "__main__":
    run_pipeline()
