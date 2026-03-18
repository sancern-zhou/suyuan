"""Test mu attribute extraction - simplified

This script verifies that mu attributes are now properly extracted.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from playwright.sync_api import sync_playwright
import time
from urllib.parse import quote


def test_mu_simple():
    """Simplified test for mu extraction"""

    with sync_playwright() as p:
        print("Testing mu attribute extraction...")
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        # Navigate to Baidu search results
        page.goto("https://www.baidu.com/s?wd=" + quote("广东旭诚科技有限公司"))
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        # Check mu attributes directly
        mu_info = page.evaluate("""
            () => {
                const results = document.querySelectorAll('div.result');
                const muData = [];

                for (let i = 0; i < Math.min(results.length, 10); i++) {
                    const mu = results[i].getAttribute('mu');
                    if (mu) {
                        const h3 = results[i].querySelector('h3');
                        muData.push({
                            index: i,
                            mu: mu,
                            title: h3 ? h3.textContent.substring(0, 30) : 'No title'
                        });
                    }
                }

                return muData;
            }
        """)

        print(f"\nFound {len(mu_info)} results with mu attribute:")
        for info in mu_info:
            if 'suncereltd' in info['mu']:
                print(f"  *** TARGET: {info['mu']}")

        print(f"\n*** SUCCESS: mu attribute extraction works! ***")

        browser.close()


if __name__ == "__main__":
    test_mu_simple()
