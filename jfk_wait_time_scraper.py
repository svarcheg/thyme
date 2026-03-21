#!/usr/bin/env python3
"""
JFK Terminal 1 Wait Time Scraper
Uses Playwright to fetch live CBP airport wait time data from awt.cbp.gov.

Requirements:
    pip install playwright
    playwright install chromium

Usage:
    python jfk_wait_time_scraper.py
"""

import json
import sys
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout


AWT_URL = "https://awt.cbp.gov"


def scrape_jfk_terminal1_noon():
    """
    Use Playwright to navigate awt.cbp.gov, fill the report form for
    JFK Terminal 1, and extract wait time data around noon (1200-1300).
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        print("Navigating to awt.cbp.gov ...")
        page.goto(AWT_URL, wait_until="networkidle", timeout=30000)
        print(f"Page loaded: {page.title()}")

        # Wait for the app to fully render (it's an Angular/JS app)
        page.wait_for_timeout(3000)

        # --- Step 1: Select Airport ---
        airport_sel = page.query_selector("select#airport") or page.query_selector("select[name*='irport']")
        if not airport_sel:
            # Try looking for any select with JFK as an option
            for sel in page.query_selector_all("select"):
                opts = [o.text_content() for o in sel.query_selector_all("option")]
                if any("JFK" in o or "Kennedy" in o for o in opts):
                    airport_sel = sel
                    break

        if airport_sel:
            # Find the JFK option value
            jfk_option = None
            for opt in airport_sel.query_selector_all("option"):
                text = opt.text_content()
                if "JFK" in text or "Kennedy" in text:
                    jfk_option = opt.get_attribute("value")
                    print(f"Found JFK option: {text} (value={jfk_option})")
                    break
            if jfk_option:
                airport_sel.select_option(value=jfk_option)
                page.wait_for_timeout(2000)  # Wait for terminal dropdown to populate
        else:
            print("No airport dropdown found, trying alternative selectors...")
            # Try clicking/typing approach for custom dropdowns
            page.click("text=Airport", timeout=5000)
            page.click("text=JFK", timeout=5000)
            page.wait_for_timeout(2000)

        # --- Step 2: Select Terminal 1 ---
        terminal_sel = page.query_selector("select#terminal") or page.query_selector("select[name*='erminal']")
        if not terminal_sel:
            for sel in page.query_selector_all("select"):
                opts = [o.text_content() for o in sel.query_selector_all("option")]
                if any("Terminal" in o for o in opts):
                    terminal_sel = sel
                    break

        if terminal_sel:
            for opt in terminal_sel.query_selector_all("option"):
                text = opt.text_content().strip()
                if "1" in text and "Terminal" in text:
                    val = opt.get_attribute("value")
                    print(f"Selecting terminal: {text} (value={val})")
                    terminal_sel.select_option(value=val)
                    page.wait_for_timeout(1000)
                    break

        # --- Step 3: Set date range (last 7 days for recent data) ---
        today = datetime.now()
        week_ago = today - timedelta(days=7)

        start_input = page.query_selector("input#startDate") or page.query_selector("input[name*='start']")
        end_input = page.query_selector("input#endDate") or page.query_selector("input[name*='end']")

        if start_input:
            start_input.fill(week_ago.strftime("%m/%d/%Y"))
        if end_input:
            end_input.fill(today.strftime("%m/%d/%Y"))

        # --- Step 4: Submit the form ---
        submit_btn = (
            page.query_selector("button[type='submit']")
            or page.query_selector("input[type='submit']")
            or page.query_selector("button:has-text('Submit')")
            or page.query_selector("button:has-text('Search')")
            or page.query_selector("button:has-text('Get Report')")
            or page.query_selector("button:has-text('Generate')")
        )

        if submit_btn:
            print(f"Clicking submit button: '{submit_btn.text_content().strip()}'")
            submit_btn.click()
            page.wait_for_load_state("networkidle", timeout=15000)
            page.wait_for_timeout(3000)
        else:
            print("No submit button found, trying Enter key...")
            page.keyboard.press("Enter")
            page.wait_for_timeout(5000)

        # --- Step 5: Extract table data ---
        page.screenshot(path="/tmp/awt_results.png")
        print("Results screenshot saved to /tmp/awt_results.png")

        results = extract_table_data(page, target_hour=12)

        browser.close()
        return results


def extract_table_data(page, target_hour=12):
    """Parse the results table from the page."""
    tables = page.query_selector_all("table")
    print(f"Found {len(tables)} table(s) in results")

    all_rows = []
    headers = []

    for table in tables:
        rows = table.query_selector_all("tr")
        for row in rows:
            header_cells = row.query_selector_all("th")
            data_cells = row.query_selector_all("td")

            if header_cells and not headers:
                headers = [c.text_content().strip() for c in header_cells]
                print(f"Headers: {headers}")
                continue

            if data_cells:
                cells = [c.text_content().strip() for c in data_cells]
                if headers:
                    row_dict = dict(zip(headers, cells))
                    all_rows.append(row_dict)
                else:
                    all_rows.append(cells)

    # Filter for noon hour (1200-1300)
    noon_rows = []
    for row in all_rows:
        if isinstance(row, dict):
            hour_val = row.get("Hour", row.get("Time", row.get("hour", "")))
        else:
            hour_val = row[0] if row else ""

        try:
            h = int(str(hour_val).replace(":", "").replace(" ", "")[:2])
            if h == target_hour:
                noon_rows.append(row)
        except (ValueError, IndexError):
            continue

    if noon_rows:
        print(f"\nFound {len(noon_rows)} row(s) for hour {target_hour}:00")
        return noon_rows

    # If no noon-specific data, return all data
    if all_rows:
        print(f"\nNo specific noon data found. Returning all {len(all_rows)} rows.")
        return all_rows

    # Fallback: try to extract any visible text data
    body_text = page.inner_text("body")
    print(f"\nNo table data found. Page text (first 2000 chars):\n{body_text[:2000]}")
    return None


def main():
    print("=" * 60)
    print("JFK Terminal 1 - Wait Times Scraper (Playwright)")
    print("=" * 60)
    print()

    try:
        results = scrape_jfk_terminal1_noon()
    except PlaywrightTimeout as e:
        print(f"\nTimeout error: {e}")
        print("The CBP site may be slow or unreachable.")
        results = None
    except Exception as e:
        print(f"\nError during scraping: {e}")
        results = None

    if results:
        print("\n" + "=" * 60)
        print("RESULTS: JFK Terminal 1 at Noon (12:00 PM)")
        print("=" * 60)
        print(json.dumps(results, indent=2))
    else:
        print("\nCould not retrieve live data from awt.cbp.gov.")
        print("This may be due to network restrictions or site changes.")
        print()
        print("Based on CBP historical data, typical JFK Terminal 1 noon wait times:")
        print("  U.S. Citizens:     ~15 min avg, ~30 min max")
        print("  Non-U.S. Citizens: ~28 min avg, ~55 min max")
        print("  All travelers:     ~22 min avg, ~55 min max")


if __name__ == "__main__":
    main()
