import sys
import os

# Add the current directory to sys.path to resolve imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from scraper import get_combined_reviews
from analyzer import get_sample, generate_themes, classify_and_tag
from aggregator import aggregate_results, save_kb

def run_test_pipeline():
    """Executes a balanced Phase 1 pipeline for testing."""
    print("Starting Balanced Test Review Intelligence Pipeline...")
    
    # Fetch reviews
    # scraper.py default is now 40 weeks
    all_reviews = get_combined_reviews()
    if not all_reviews:
        print("No reviews found. Exiting.")
        return
    
    # Balanced sampling for the test run
    play_reviews = [r for r in all_reviews if r.source == 'playstore']
    app_reviews = [r for r in all_reviews if r.source == 'appstore']
    
    import random
    # Take up to 50 from each for a diverse test set of 100
    test_set = random.sample(play_reviews, min(len(play_reviews), 50))
    test_set += random.sample(app_reviews, min(len(app_reviews), 50))
    
    random.shuffle(test_set)
    print(f"Testing with {len(test_set)} total reviews ({len([r for r in test_set if r.source == 'playstore'])} Play Store, {len([r for r in test_set if r.source == 'appstore'])} App Store).")
    
    # Stage 2: Sample for theme generation
    sample = get_sample(test_set, sample_size=20)
    print(f"Sampled {len(sample)} reviews for theme discovery.")
    
    # Stage 3: Theme Generation
    print("Generating themes...")
    themes = generate_themes(sample)
    print(f"Discovered {len(themes)} themes.")
    
    if not themes:
        print("No themes discovered. Using fallback themes.")
        from analyzer import Theme
        themes = [
            Theme(theme_name="Withdrawal", short_description="Funds withdrawal issues", example_phrases=["money", "withdrawal"]),
            Theme(theme_name="Dashboard", short_description="App interface and data", example_phrases=["view", "balance"])
        ]
    
    # Stage 4: Classification & Tagging
    print("Classifying and tagging reviews...")
    classified_data = classify_and_tag(test_set, themes)
    
    # Stage 5: Aggregate & Persist
    print("Aggregating results...")
    kb_data = aggregate_results(classified_data, themes)
    save_kb(kb_data)
    
    print("Test Pipeline completed successfully!")
    return kb_data

if __name__ == "__main__":
    run_test_pipeline()
