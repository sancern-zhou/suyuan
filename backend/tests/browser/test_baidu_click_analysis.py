"""Deep analysis of Baidu search results click behavior

This script analyzes why clicks on Baidu search results don't navigate properly.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from playwright.sync_api import sync_playwright
import time
from urllib.parse import quote


def test_baidu_click_analysis():
    """Analyze Baidu search results click behavior"""

    with sync_playwright() as p:
        print("Starting browser...")
        browser = p.chromium.launch(headless=False, slow_mo=2000)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        page = context.new_page()

        print("\n1. Navigating to Baidu search results...")
        search_term = "广东旭诚科技有限公司"
        search_url = f"https://www.baidu.com/s?wd={quote(search_term)}"
        page.goto(search_url)

        print("2. Waiting for page load...")
        page.wait_for_load_state("networkidle")
        time.sleep(3)

        print("\n3. Detailed analysis of search results:\n")

        # Analyze the structure of search results
        results_analysis = page.evaluate("""
            () => {
                const results = [];

                // Try different selectors
                const selectors = [
                    'div.result',
                    'div[class*="result"]',
                    'div.result.c-container',
                    'div.c-container'
                ];

                selectors.forEach(selector => {
                    try {
                        const elements = document.querySelectorAll(selector);
                        if (elements.length > 0) {
                            results.push({
                                selector: selector,
                                count: elements.length,
                                firstElementHTML: elements[0].outerHTML.substring(0, 200)
                            });
                        }
                    } catch (e) {
                        // Ignore errors
                    }
                });

                return results;
            }
        """)

        print("Search result containers found:")
        for result in results_analysis:
            print(f"  Selector: {result['selector']}")
            print(f"  Count: {result['count']}")
            print(f"  First element HTML: {result['firstElementHTML']}")
            print()

        # Test specific click scenarios
        print("4. Testing click scenarios:\n")

        # Scenario 1: Click first result link directly
        print("[Scenario 1] Click first result with direct link")
        try:
            first_result = page.locator("div.result").first
            first_link = first_result.locator("h3 a").first

            if first_link.count() > 0:
                link_text = first_link.inner_text()
                link_href = first_link.get_attribute("href")

                print(f"  Link text: {link_text[:50]}")
                print(f"  Link href: {link_href[:80] if link_href else 'None'}")

                # Check if it's a Baidu redirect link
                if link_href and "baidu.com/link?url=" in link_href:
                    print(f"  -> This is a Baidu redirect link")

                    # Extract actual URL from Baidu redirect
                    try:
                        from urllib.parse import unquote, urlparse, parse_qs
                        parsed = urlparse(link_href)
                        actual_url = unquote(parse_qs(parsed.query)['url'][0])
                        print(f"  -> Actual URL: {actual_url}")
                    except:
                        pass

                # Setup navigation handler
                navigated_url = None

                def handle_navigation(route):
                    nonlocal navigated_url
                    if "suncereltd.com" in route.request.url or "旭诚" in route.request.url:
                        navigated_url = route.request.url
                        print(f"  -> Navigation to: {route.request.url}")
                    else:
                        print(f"  -> Navigation to: {route.request.url}")
                    route.continue_()

                page.on("request", handle_navigation)

                # Try the click
                try:
                    first_link.click(timeout=10000)
                    time.sleep(3)

                    print(f"  -> After click, current URL: {page.url}")

                    if navigated_url:
                        print(f"  -> SUCCESS: Navigated to target URL")
                    elif "baidu.com" in page.url:
                        print(f"  -> Still on Baidu, possibly opened in new tab")
                    else:
                        print(f"  -> Unexpected URL")

                except Exception as e:
                    print(f"  -> Click failed: {e}")

        except Exception as e:
            print(f"  -> Scenario failed: {e}")

        # Scenario 2: Check if links open in new tab
        print("\n[Scenario 2] Check if links open in new tab")
        page.goto(search_url)
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        try:
            # Check target attribute of links
            link_targets = page.evaluate("""
                () => {
                    const links = document.querySelectorAll('div.result h3 a, div.result a[class*="title"]');
                    const targets = [];

                    for (let i = 0; i < Math.min(links.length, 5); i++) {
                        const link = links[i];
                        targets.push({
                            index: i,
                            text: link.textContent.substring(0, 30),
                            target: link.getAttribute('target'),
                            href: link.getAttribute('href'),
                            onclick: link.getAttribute('onclick') != null
                        });
                    }

                    return targets;
                }
            """)

            print("Link attributes:")
            for link_info in link_targets:
                print(f"  [{link_info['index']}] {link_info['text']}")
                print(f"      Target: {link_info['target']}")
                print(f"      Has onclick: {link_info['onclick']}")

        except Exception as e:
            print(f"  -> Analysis failed: {e}")

        # Scenario 3: Try extracting URL and navigating directly
        print("\n[Scenario 3] Extract URL and navigate directly")
        page.goto(search_url)
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        try:
            # Find the actual URL from search results
            actual_url = page.evaluate("""
                () => {
                    const searchTerm = "广东旭诚";

                    // Find h3 containing company name
                    const h3s = document.querySelectorAll('h3');
                    for (let h3 of h3s) {
                        if (h3.textContent.includes(searchTerm)) {
                            const link = h3.querySelector('a');
                            if (link) {
                                const href = link.getAttribute('href');
                                if (href && href.includes('baidu.com/link?url=')) {
                                    // Extract actual URL from Baidu redirect
                                    const urlMatch = href.match(/url=([^&]+)/);
                                    if (urlMatch) {
                                        return decodeURIComponent(urlMatch[1]);
                                    }
                                } else if (href && href.startsWith('http')) {
                                    return href;
                                }
                            }
                        }
                    }

                    return null;
                }
            """)

            if actual_url:
                print(f"  -> Extracted URL: {actual_url}")

                # Navigate directly
                print(f"  -> Navigating directly to URL...")
                page.goto(actual_url, wait_until="domcontentloaded")

                time.sleep(3)

                print(f"  -> Current URL: {page.url}")

                if "suncereltd.com" in page.url or "旭诚" in page.url:
                    print(f"  -> SUCCESS: Direct navigation worked!")

                    # Check page content
                    page_text = page.evaluate("() => document.body.textContent")
                    if "广东旭诚" in page_text or "旭诚科技" in page_text:
                        print(f"  -> Page content confirms we're on the right site")
            else:
                print(f"  -> Could not extract URL from search results")

        except Exception as e:
            print(f"  -> Direct navigation failed: {e}")

        # Scenario 4: Try with new tab handling
        print("\n[Scenario 4] Test with new tab detection")
        page.goto(search_url)
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        try:
            # Track new pages
            new_page = None

            def handle_popup(popup):
                nonlocal new_page
                print(f"  -> New tab/page detected!")
                new_page = popup

            context.on("page", handle_popup)

            # Click the first result
            first_result = page.locator("div.result").first
            first_link = first_result.locator("h3 a").first

            if first_link.count() > 0:
                first_link.click()
                time.sleep(3)

                if new_page:
                    print(f"  -> New page URL: {new_page.url}")
                    if "suncereltd.com" in new_page.url or "旭诚" in new_page.url:
                        print(f"  -> SUCCESS: Link opened in new tab!")
                    new_page.close()
                else:
                    print(f"  -> No new page detected")
                    print(f"  -> Current page URL: {page.url}")

        except Exception as e:
            print(f"  -> New tab test failed: {e}")

        print("\n5. Final state:")
        print(f"Current URL: {page.url}")
        print(f"Page title: {page.title()}")

        print("\n6. Waiting 5 seconds for manual inspection...")
        time.sleep(5)

        context.close()
        browser.close()
        print("\nTest completed!")


if __name__ == "__main__":
    test_baidu_click_analysis()
