"""Test Baidu search results page interaction

This script tests different methods to interact with Baidu search results.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from playwright.sync_api import sync_playwright
import time
from urllib.parse import quote


def test_baidu_search_results():
    """Test interacting with Baidu search results page"""

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

        print("\n3. Analyzing search results structure:\n")

        # Test different selectors for search results
        selectors_to_test = [
            ("Result container (old)", "div.result"),
            ("Result container (new)", "div[class*='result']"),
            ("Result container (c-container)", "div.result.c-container"),
            ("Result container (xpath)", "xpath=//div[@class='result']"),
            ("Title links", "h3 a"),
            ("Title links (class)", "a[class*='title']"),
            ("All links in results", "div.result a"),
        ]

        found_selectors = []

        for name, selector in selectors_to_test:
            try:
                if selector.startswith("xpath="):
                    elements = page.locator(selector).count()
                else:
                    elements = page.locator(selector).count()

                if elements > 0:
                    print(f"[OK] {name:30} | {selector:40} | Found: {elements} items")
                    found_selectors.append((name, selector, elements))
                else:
                    print(f"[FAIL] {name:30} | {selector:40} | Not found")
            except Exception as e:
                print(f"[ERROR] {name:30} | {selector:40} | {str(e)[:30]}")

        print(f"\n4. Found {len(found_selectors)} working selectors")

        # Test extracting link information
        print("\n5. Extracting search result links:\n")

        if found_selectors:
            # Use the best selector
            best_selector = found_selectors[0][1]

            links = page.evaluate(f"""
                () => {{
                    const links = [];
                    const results = document.querySelectorAll("{best_selector} a");

                    for (let i = 0; i < Math.min(results.length, 10); i++) {{
                        const link = results[i];
                        links.push({{
                            index: i,
                            text: link.textContent.substring(0, 50),
                            href: link.href,
                            class: link.className,
                            visible: link.offsetParent !== null
                        }});
                    }}

                    return links;
                }}
            """)

            print(f"Found {len(links)} links:")
            for link in links:
                visible = "VISIBLE" if link['visible'] else "HIDDEN"
                print(f"  [{link['index']}] {visible}: {link['text']}")
                print(f"      URL: {link['href'][:60]}...")
                print(f"      Class: {link['class']}")

        # Test different methods to click a result
        print("\n6. Testing different click methods:\n")

        # Method 1: Use text selector
        print("[Method 1] Using text selector")
        try:
            # Try to find link containing the company name
            text_selector = f"a:has-text('{search_term}')"
            element = page.locator(text_selector).first

            if element.count() > 0:
                print(f"  -> Found element with text selector")
                element.click(timeout=5000)
                print(f"  -> SUCCESS: Clicked using text selector")

                time.sleep(2)
                print(f"  -> Current URL: {page.url}")

                if "suncereltd.com" in page.url or "旭诚" in page.url:
                    print(f"  -> Successfully navigated to company website!")
            else:
                print(f"  -> No element found with text selector")
        except Exception as e:
            print(f"  -> FAILED: {e}")

        # If not on company website yet, go back and try method 2
        if "suncereltd.com" not in page.url and "旭诚" not in page.url:
            page.go_back()
            time.sleep(2)

            print("\n[Method 2] Using h3 text selector")
            try:
                # Find h3 containing company name
                h3_selector = f"h3:has-text('{search_term}')"
                h3 = page.locator(h3_selector).first

                if h3.count() > 0:
                    print(f"  -> Found h3 with company name")

                    # Find the link inside the h3
                    link_in_h3 = h3.locator("a")
                    link_in_h3.click(timeout=5000)
                    print(f"  -> SUCCESS: Clicked link inside h3")

                    time.sleep(2)
                    print(f"  -> Current URL: {page.url}")

                    if "suncereltd.com" in page.url or "旭诚" in page.url:
                        print(f"  -> Successfully navigated to company website!")
                else:
                    print(f"  -> No h3 found with company name")
            except Exception as e:
                print(f"  -> FAILED: {e}")

        # If still not on company website, try method 3
        if "suncereltd.com" not in page.url and "旭诚" not in page.url:
            page.go_back()
            time.sleep(2)

            print("\n[Method 3] Using JavaScript to find and click")
            try:
                result = page.evaluate(f"""
                    () => {{
                        const searchTerm = "{search_term}";

                        // Find all h3 elements
                        const h3s = document.querySelectorAll('h3');

                        for (let h3 of h3s) {{
                            if (h3.textContent.includes(searchTerm)) {{
                                // Find the link inside this h3
                                const link = h3.querySelector('a');
                                if (link) {{
                                    link.click();
                                    return {{
                                        success: true,
                                        text: h3.textContent.substring(0, 50),
                                        url: link.href
                                    }};
                                }}
                            }}
                        }}

                        return {{ success: false }};
                    }}
                """)

                if result['success']:
                    print(f"  -> SUCCESS: Clicked using JavaScript")
                    print(f"  -> Text: {result['text']}")
                    print(f"  -> URL: {result['url']}")

                    time.sleep(2)
                    print(f"  -> Current URL: {page.url}")

                    if "suncereltd.com" in page.url or "旭诚" in page.url:
                        print(f"  -> Successfully navigated to company website!")
                else:
                    print(f"  -> FAILED: Could not find link")

            except Exception as e:
                print(f"  -> FAILED: {e}")

        # Method 4: Try using nth selector if we know the position
        if "suncereltd.com" not in page.url and "旭诚" not in page.url:
            page.go_back()
            time.sleep(2)

            print("\n[Method 4] Using nth selector (first result)")
            try:
                # Try clicking the first search result
                first_result = page.locator("div.result").first
                first_link = first_result.locator("h3 a").first

                if first_link.count() > 0:
                    print(f"  -> Found first result link")

                    link_text = first_link.text_content()
                    print(f"  -> Link text: {link_text[:50]}")

                    first_link.click(timeout=5000)
                    print(f"  -> SUCCESS: Clicked first result")

                    time.sleep(2)
                    print(f"  -> Current URL: {page.url}")
                else:
                    print(f"  -> No first result found")

            except Exception as e:
                print(f"  -> FAILED: {e}")

        # Check for certificate warnings or dialogs
        print("\n7. Checking for dialogs or warnings:\n")

        dialogs = page.evaluate("""
            () => {
                const results = {
                    hasDialog: false,
                    dialogs: []
                };

                // Check for common dialogs
                const selectors = [
                    '.dialog', '.modal', '.overlay',
                    '[role="dialog"]', '[role="alert"]',
                    '.cert-warning', '.security-warning'
                ];

                selectors.forEach(selector => {
                    const elements = document.querySelectorAll(selector);
                    elements.forEach(el => {
                        results.hasDialog = true;
                        results.dialogs.push({
                            selector: selector,
                            text: el.textContent.substring(0, 100),
                            display: window.getComputedStyle(el).display
                        });
                    });
                });

                return results;
            }
        """)

        if dialogs['hasDialog']:
            print(f"  Found {len(dialogs['dialogs'])} dialogs/warnings:")
            for dialog in dialogs['dialogs']:
                print(f"    - {dialog['selector']}: {dialog['text'][:50]}")
        else:
            print(f"  No dialogs or warnings detected")

        # Final state check
        print("\n8. Final state check:\n")
        print(f"Current URL: {page.url}")

        if "suncereltd.com" in page.url or "旭诚" in page.url:
            print(f"STATUS: SUCCESS - Successfully navigated to company website")
        else:
            print(f"STATUS: INCOMPLETE - Still on search results or other page")

        print("\n9. Waiting 5 seconds for manual inspection...")
        time.sleep(5)

        browser.close()
        print("\nTest completed!")


if __name__ == "__main__":
    test_baidu_search_results()
