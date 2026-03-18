"""Test mu attribute extraction after fix

This script tests if the mu attribute is now properly extracted.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from playwright.sync_api import sync_playwright
import time
from urllib.parse import quote


def test_mu_extraction():
    """Test if mu attribute is extracted in snapshot"""

    with sync_playwright() as p:
        print("Starting browser...")
        browser = p.chromium.launch(headless=False, slow_mo=1000)
        page = browser.new_page()

        print("\n1. Navigating to Baidu search results...")
        search_term = "广东旭诚科技有限公司"
        search_url = f"https://www.baidu.com/s?wd={quote(search_term)}"
        page.goto(search_url)

        print("2. Waiting for page load...")
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        print("\n3. Testing mu attribute extraction:\n")

        # Test our RoleRef implementation
        from app.tools.browser.refs.role_ref import RoleRef
        from app.tools.browser.snapshot.formatters.ai_formatter import AIFormatter

        # Create a snapshot
        formatter = AIFormatter()
        result = formatter.format(page, max_refs=100, interactive_only=False, depth=10, compact=True)

        print(f"Snapshot stats:")
        print(f"  Total refs: {result['stats']['total_refs']}")
        print(f"  Interactive refs: {result['stats']['interactive_refs']}")

        print(f"\n4. Checking if mu attributes are in refs:\n")

        # Check if any refs have mu attribute
        has_mu_count = 0
        mu_urls = []

        for ref_id, ref_data in result['refs'].items():
            if 'html_attrs' in ref_data and 'mu' in ref_data['html_attrs']:
                has_mu_count += 1
                mu = ref_data['html_attrs']['mu']
                mu_urls.append({
                    'ref_id': ref_id,
                    'mu': mu,
                    'name': ref_data.get('name', '')
                })

                if 'suncereltd.com' in mu:
                    print(f"  *** TARGET FOUND ***")
                    print(f"  Ref ID: {ref_id}")
                    print(f"  Name: {ref_data.get('name', '')}")
                    print(f"  MU (URL): {mu}")

        print(f"\n5. Summary:")
        print(f"  Total refs with mu attribute: {has_mu_count}")
        print(f"  Target URLs found: {len([u for u in mu_urls if 'suncereltd.com' in u['mu']])}")

        # Show first few mu URLs
        if mu_urls:
            print(f"\n6. First 5 mu URLs:")
            for i, url_info in enumerate(mu_urls[:5]):
                print(f"  [{i}] {url_info['ref_id']}: {url_info['mu'][:80]}")
                if url_info['name']:
                    print(f"      Name: {url_info['name'][:50]}")

        # Test if Agent can now use mu to navigate
        print(f"\n7. Testing navigation using mu attribute:")

        target_mu = None
        for url_info in mu_urls:
            if 'suncereltd.com' in url_info['mu']:
                target_mu = url_info['mu']
                print(f"  Target mu found: {target_mu}")

                # Navigate directly
                page.goto(target_mu, wait_until="domcontentloaded")
                time.sleep(2)

                current_url = page.url
                print(f"  After navigation: {current_url}")

                if "suncereltd.com" in current_url:
                    print(f"  *** SUCCESS: Direct navigation using mu attribute works! ***")
                break

        print("\n8. Waiting 3 seconds before closing...")
        time.sleep(3)

        browser.close()
        print("\nTest completed!")


if __name__ == "__main__":
    test_mu_extraction()
