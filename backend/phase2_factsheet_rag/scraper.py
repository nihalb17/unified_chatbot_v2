"""
Phase 2 — Factsheet & Definition Scrapers

Scrapes Groww factsheet pages (14 fields per scheme) and definition pages.
"""

import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone

# Browser-like headers to avoid being blocked
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# The 14 fields to extract from each factsheet page
FACTSHEET_FIELDS = [
    "Lock-in",
    "NAV",
    "Minimum SIP",
    "Fund Size",
    "Expense Ratio",
    "Alpha",
    "Beta",
    "Sharpe",
    "Sortino",
    "P/E Ratio",
    "P/B Ratio",
    "Exit Load",
    "Stamp Duty",
    "Fund Management",
]

# Mapping of field names to possible label text on the page
FIELD_LABEL_VARIANTS = {
    "Lock-in": ["lock-in", "lock in", "lockin"],
    "NAV": ["nav"],
    "Minimum SIP": ["min. for sip", "min sip", "minimum sip", "min. sip"],
    "Fund Size": ["fund size", "fund size (aum)", "aum"],
    "Expense Ratio": ["expense ratio"],
    "Alpha": ["alpha"],
    "Beta": ["beta"],
    "Sharpe": ["sharpe", "sharpe ratio"],
    "Sortino": ["sortino", "sortino ratio"],
    "P/E Ratio": ["p/e ratio", "p/e", "pe ratio"],
    "P/B Ratio": ["p/b ratio", "p/b", "pb ratio"],
    "Exit Load": ["exit load"],
    "Stamp Duty": ["stamp duty", "stamp duty on investment"],
    "Fund Management": ["fund management", "fund manager", "fund managers"],
}


def extract_scheme_name_from_url(url: str) -> str:
    """Extract a human-readable scheme name from a Groww mutual fund URL slug."""
    # e.g. https://groww.in/mutual-funds/axis-elss-tax-saver-direct-plan-growth
    slug = url.rstrip("/").split("/")[-1]
    # Replace hyphens with spaces and title case
    name = slug.replace("-", " ").title()
    return name


def scrape_factsheet(url: str) -> dict | None:
    """
    Scrape a Groww factsheet page and extract the 14 specified fields.
    
    Uses Groww's embedded __NEXT_DATA__ JSON and inline scripts for reliable,
    structured extraction instead of fragile HTML element traversal.
    
    Returns:
        {
            "scheme_name": str,
            "fields": { "NAV": "₹106.07", "Alpha": "0.22", ... },
            "source_url": str,
            "scraped_at": str (ISO timestamp)
        }
        or None on failure.
    """
    try:
        print(f"  [Scraper] Fetching: {url}")
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        
        soup = BeautifulSoup(resp.text, "html.parser")
        
        # --- Primary strategy: Extract from __NEXT_DATA__ JSON ---
        mf_data = _extract_next_data(soup)
        
        if mf_data:
            return _build_factsheet_from_json(mf_data, soup, url)
        
        # --- Fallback: legacy HTML scraping (if __NEXT_DATA__ is absent) ---
        print(f"  [Scraper] __NEXT_DATA__ not found, falling back to HTML scraping for {url}")
        return _scrape_factsheet_html(soup, url)
        
    except Exception as e:
        print(f"  [Scraper] FAILED for {url}: {e}")
        return None


def _extract_next_data(soup) -> dict | None:
    """Extract the mfServerSideData from __NEXT_DATA__ script tag."""
    import json as _json
    nd = soup.find("script", id="__NEXT_DATA__")
    if not nd:
        return None
    try:
        data = _json.loads(nd.get_text())
        return data["props"]["pageProps"]["mfServerSideData"]
    except (KeyError, _json.JSONDecodeError):
        return None


def _extract_ratios_from_inline_script(soup) -> dict:
    """Extract Alpha, Beta, Sharpe, Sortino from inline script JSON objects."""
    import json as _json
    ratios = {}
    for script in soup.find_all("script"):
        txt = script.get_text()
        if '"alpha"' in txt and '"sharpe_ratio"' in txt:
            idx = txt.find('"alpha"')
            # Walk backward to find the enclosing '{'
            start = idx
            for i in range(idx, -1, -1):
                if txt[i] == '{':
                    start = i
                    break
            # Walk forward to find the matching '}'
            brace_count = 0
            end = start
            for i in range(start, len(txt)):
                if txt[i] == '{':
                    brace_count += 1
                elif txt[i] == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end = i + 1
                        break
            try:
                obj = _json.loads(txt[start:end])
                for json_key, field_name in [
                    ("alpha", "Alpha"),
                    ("beta", "Beta"),
                    ("sharpe_ratio", "Sharpe"),
                    ("sortino_ratio", "Sortino"),
                    ("pe_ratio", "P/E Ratio"),
                    ("pb_ratio", "P/B Ratio"),
                ]:
                    val = obj.get(json_key)
                    if val is not None:
                        ratios[field_name] = str(round(val, 4))
            except (_json.JSONDecodeError, ValueError):
                pass
            break
    return ratios


def _build_factsheet_from_json(mf: dict, soup, url: str) -> dict:
    """Build the factsheet result dict from __NEXT_DATA__ JSON + inline scripts."""
    scheme_name = mf.get("scheme_name") or extract_scheme_name_from_url(url)
    fields = {}
    
    # --- Direct fields from mfServerSideData ---
    nav = mf.get("nav")
    nav_date = mf.get("nav_date")
    if nav is not None:
        fields["NAV"] = f"₹{nav}" + (f" (as of {nav_date})" if nav_date else "")
    
    min_sip = mf.get("min_sip_investment")
    if min_sip is not None:
        fields["Minimum SIP"] = f"₹{min_sip}"
    
    aum = mf.get("aum")
    if aum is not None:
        fields["Fund Size"] = f"₹{aum:,.2f} Cr"
    
    expense = mf.get("expense_ratio")
    if expense is not None:
        fields["Expense Ratio"] = f"{expense}%"
    
    exit_load = mf.get("exit_load")
    if exit_load:
        fields["Exit Load"] = exit_load
    
    stamp_duty = mf.get("stamp_duty")
    if stamp_duty:
        fields["Stamp Duty"] = stamp_duty
    
    # Lock-in
    lock_in = mf.get("lock_in")
    if lock_in and isinstance(lock_in, dict):
        years = lock_in.get("years")
        months = lock_in.get("months")
        days = lock_in.get("days")
        parts = []
        if years: parts.append(f"{years}Y")
        if months: parts.append(f"{months}M")
        if days: parts.append(f"{days}D")
        if parts:
            fields["Lock-in"] = " ".join(parts) + " Lock-in"
    
    # Fund managers
    fm_details = mf.get("fund_manager_details", [])
    if fm_details:
        manager_strs = []
        for fm in fm_details:
            name = fm.get("person_name", "")
            if name:
                manager_strs.append(name)
        if manager_strs:
            fields["Fund Management"] = ", ".join(manager_strs)
    
    # --- Ratios from inline script (Alpha, Beta, Sharpe, Sortino, P/E, P/B) ---
    ratios = _extract_ratios_from_inline_script(soup)
    fields.update(ratios)
    
    print(f"  [Scraper] Extracted {len(fields)}/{len(FACTSHEET_FIELDS)} fields for {scheme_name}")
    
    return {
        "scheme_name": scheme_name,
        "fields": fields,
        "source_url": url,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }


def _scrape_factsheet_html(soup, url: str) -> dict | None:
    """Legacy fallback: extract fields from HTML elements when JSON is unavailable."""
    page_text = soup.get_text(" ", strip=True)
    
    scheme_name = None
    h1 = soup.find("h1")
    if h1:
        scheme_name = h1.get_text(strip=True)
    if not scheme_name:
        scheme_name = extract_scheme_name_from_url(url)
    
    fields = {}
    all_elements = soup.find_all(["div", "span", "td", "p", "li", "h2", "h3", "h4"])
    
    for field_name in FACTSHEET_FIELDS:
        if field_name == "Fund Management":
            value = _extract_fund_managers(soup, page_text)
            if value:
                fields[field_name] = value
            continue
        
        if field_name == "Lock-in":
            value = _extract_lockin(page_text)
            if value:
                fields[field_name] = value
            continue
        
        variants = FIELD_LABEL_VARIANTS.get(field_name, [field_name.lower()])
        value = _extract_field_value(all_elements, variants)
        if value:
            fields[field_name] = value
    
    print(f"  [Scraper] Extracted {len(fields)}/{len(FACTSHEET_FIELDS)} fields for {scheme_name}")
    
    return {
        "scheme_name": scheme_name,
        "fields": fields,
        "source_url": url,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }


def _extract_field_value(elements, label_variants: list[str]) -> str | None:
    """Find a field value by matching label text in elements."""
    for el in elements:
        # Ignore container elements that have multiple child tags to prevent matching parent rows
        if len(el.find_all(recursive=False)) >= 2:
            continue
            
        el_text = el.get_text(strip=True).lower()
        
        for variant in label_variants:
            if variant == el_text or el_text.startswith(variant):
                # Found the label — look for the value in siblings or parent
                # Strategy 1: Next sibling element
                next_el = el.find_next_sibling()
                if next_el:
                    val = next_el.get_text(strip=True)
                    if val and val.lower() != el_text and len(val) < 200:
                        return val
                
                # Strategy 2: Parent's next sibling or child
                parent = el.parent
                if parent:
                    next_parent = parent.find_next_sibling()
                    if next_parent:
                        val = next_parent.get_text(strip=True)
                        if val and len(val) < 200:
                            return val
                    
                    # Strategy 3: all children of parent, take the last meaningful one
                    children = parent.find_all(recursive=False)
                    if len(children) >= 2:
                        val = children[-1].get_text(strip=True)
                        if val and val.lower() != el_text and len(val) < 200:
                            return val
    
    return None


def _extract_lockin(page_text: str) -> str | None:
    """Extract lock-in period from page text (e.g., '3Y Lock-in')."""
    match = re.search(r'(\d+[Yy]\s*lock[\s-]*in)', page_text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    
    match = re.search(r'lock[\s-]*in[:\s]*(\d+\s*(?:year|yr|Y)s?)', page_text, re.IGNORECASE)
    if match:
        return match.group(0).strip()
    
    return None


def _extract_fund_managers(soup, page_text: str) -> str | None:
    """Extract fund manager names from the page."""
    # Look for elements that contain "Fund management" or "Fund manager"
    for el in soup.find_all(["div", "h2", "h3", "h4", "span"]):
        text = el.get_text(strip=True).lower()
        if text in ("fund management", "fund manager", "fund managers"):
            # Look in the parent container for manager name elements
            parent = el.parent
            if parent:
                # Get all text blocks in the parent section that look like names
                container = parent.parent if parent.parent else parent
                names = []
                for child in container.find_all(["div", "span", "a"]):
                    child_text = child.get_text(strip=True)
                    # Filter for name-like text (not labels, not empty, reasonable length)
                    if (child_text and 
                        child_text.lower() not in ("fund management", "fund manager", "fund managers", "") and
                        2 < len(child_text) < 50 and
                        not child_text.startswith("http") and
                        any(c.isalpha() for c in child_text)):
                        # Avoid duplicates
                        if child_text not in names:
                            names.append(child_text)
                
                if names:
                    return ", ".join(names[:5])  # cap at 5 managers
    
    return None


def scrape_definition(url: str, term: str) -> dict | None:
    """
    Scrape a Groww definition/explainer page.
    
    Args:
        url: The definition page URL
        term: The term name (provided by the user, not inferred)
    
    Returns:
        {
            "term": str,
            "text": str (definition content),
            "source_url": str,
            "scraped_at": str
        }
        or None on failure.
    """
    try:
        print(f"  [Scraper] Fetching definition: {url}")
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        
        soup = BeautifulSoup(resp.text, "html.parser")
        
        # Extract the main article/content body
        # Groww's /p/ pages have article content in main content area
        content = None
        
        # Try common content containers
        for selector in ["article", "main", ".content", ".article-content", "[class*='content']"]:
            container = soup.select_one(selector)
            if container:
                # Get all paragraph text
                paragraphs = container.find_all(["p", "li"])
                if paragraphs:
                    texts = [p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 20]
                    if texts:
                        content = " ".join(texts[:10])  # Take first 10 meaningful paragraphs
                        break
        
        # Fallback: get all paragraphs from the page
        if not content:
            paragraphs = soup.find_all("p")
            texts = [p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 30]
            content = " ".join(texts[:10]) if texts else None
        
        if not content:
            print(f"  [Scraper] No definition content found for '{term}' at {url}")
            return None
        
        # Truncate very long definitions
        if len(content) > 3000:
            content = content[:3000] + "..."
        
        print(f"  [Scraper] Extracted definition for '{term}' ({len(content)} chars)")
        
        return {
            "term": term,
            "text": content,
            "source_url": url,
            "scraped_at": datetime.now(timezone.utc).isoformat(),
        }
        
    except Exception as e:
        print(f"  [Scraper] FAILED for definition '{term}' at {url}: {e}")
        return None
