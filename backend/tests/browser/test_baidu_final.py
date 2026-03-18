"""Final test for Baidu search results - Direct URL extraction

This script tests extracting the actual URL from Baidu search results.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from playwright.sync_api import sync_playwright
import time
from urllib.parse import quote


def test_baidu_final():
    """Final test for Baidu search results"""

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

        print("\n3. Extracting URLs from search results:\n")

        # Method 1: Extract from mu attribute (most reliable)
        print("[Method 1] Extract from mu attribute")

        urls = page.evaluate("""
            () => {
                const results = [];

                // Find all result containers
                const containers = document.querySelectorAll('div.result');

                for (let i = 0; i < Math.min(containers.length, 10); i++) {
                    const container = containers[i];

                    // Try to get URL from mu attribute
                    const mu = container.getAttribute('mu');
                    if (mu) {
                        const h3 = container.querySelector('h3');
                        results.push({
                            method: 'mu',
                            index: i,
                            title: h3 ? h3.textContent.substring(0, 50) : 'No title',
                            url: mu
                        });
                        continue;
                    }

                    // Try to get URL from data-tools
                    const dataTools = container.getAttribute('data-tools');
                    if (dataTools) {
                        try {
                            const tools = JSON.parse(dataTools.replace(/'/g, '"'));
                            if (tools.url) {
                                const h3 = container.querySelector('h3');
                                results.push({
                                    method: 'data-tools',
                                    index: i,
                                    title: h3 ? h3.textContent.substring(0, 50) : 'No title',
                                    url: tools.url
                                });
                                continue;
                            }
                        } catch (e) {
                            // Ignore
                        }
                    }

                    // Try to get URL from link href
                    const link = container.querySelector('h3 a, a[class*="title"]');
                    if (link) {
                        const href = link.getAttribute('href');
                        if (href) {
                            const h3 = container.querySelector('h3');
                            results.push({
                                method: 'href',
                                index: i,
                                title: h3 ? h3.textContent.substring(0, 50) : link.textContent.substring(0, 50),
                                url: href
                            });
                        }
                    }
                }

                return results;
            }
        """)

        print(f"Found {len(urls)} URLs:")
        for url_info in urls:
            method = url_info['method']
            title = url_info['title']
            url = url_info['url']

            print(f"\n  [{url_info['index']}] Method: {method}")
            print(f"  Title: {title}")
            print(f"  URL: {url[:80]}...")

            # Check if this is the target company
            if "suncereltd.com" in url or "旭诚" in url:
                print(f"  -> *** TARGET FOUND ***")

        print("\n4. Testing direct navigation:\n")

        # Find the target URL
        target_url = None
        for url_info in urls:
            if "suncereltd.com" in url_info['url']:
                target_url = url_info['url']
                break

        if not target_url:
            # Try second method
            for url_info in urls:
                if "旭诚" in url_info.get('title', ''):
                    target_url = url_info['url']
                    break

        if target_url:
            print(f"Target URL found: {target_url}")

            # Navigate directly
            print("Navigating to target URL...")
            page.goto(target_url, wait_until="domcontentloaded")

            time.sleep(3)

            current_url = page.url
            page_title = page.title()

            print(f"Current URL: {current_url}")
            print(f"Page title: {page_title}")

            if "suncereltd.com" in current_url or "旭诚" in current_url or "旭诚" in page_title:
                print("\n[SUCCESS] Successfully navigated to company website!")

                # Check for contact information
                print("\n5. Looking for contact information:")

                contact_info = page.evaluate("""
                    () => {
                        const phoneRegex = /电话|Tel|Contact|联系方式|手机/i;
                        const results = [];

                        // Check for phone numbers in various formats
                        const text = document.body.textContent;

                        // Common phone patterns
                        const phonePatterns = [
                            /1[3-9]\d{9}/g,  // Mobile
                            /\d{3,4}[-\s]?\d{7,8}/g,  // Landline
                            /400[-\s]?\d{3}[-\s]?\d{4}/g,  // 400 number
                        ];

                        phonePatterns.forEach(pattern => {
                            const matches = text.match(pattern);
                            if (matches) {
                                matches.forEach(match => {
                                    if (!results.includes(match)) {
                                        results.push(match);
                                    }
                                });
                            }
                        });

                        return results;
                    }
                """)

                if contact_info:
                    print(f"Found possible contact info:")
                    for info in contact_info[:5]:  # Show first 5
                        print(f"  - {info}")
                else:
                    print("No obvious contact information found")

        else:
            print("Target URL not found in search results")

        print("\n6. Waiting 5 seconds for manual inspection...")
        time.sleep(5)

        browser.close()
        print("\nTest completed!")


if __name__ == "__main__":
    test_baidu_final()
