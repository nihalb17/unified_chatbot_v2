import sys
import os
sys.path.append(r"c:\Users\nihal\Downloads\NL_Projects\Capstone_Project_v2\backend\phase2_factsheet_rag")
from scraper import scrape_factsheet

url = "https://groww.in/mutual-funds/axis-liquid-direct-fund-growth"
result = scrape_factsheet(url)

if result:
    print(f"Scheme: {result['scheme_name']}")
    print("Fields extracted:")
    for k, v in result['fields'].items():
        # Print without the rupee symbol to avoid encoding issues
        print(f"  {k}: {v.replace('₹', 'Rs.')}")
else:
    print("Failed to scrape.")
