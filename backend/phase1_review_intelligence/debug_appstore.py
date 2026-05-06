from app_store_scraper import AppStore

def test_app_store():
    print("Testing with Instagram in US...")
    try:
        insta = AppStore(country="us", app_name="instagram", app_id=389801252)
        insta.review(how_many=5)
        print(f"Successfully fetched {len(insta.reviews)} Instagram reviews.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_app_store()
