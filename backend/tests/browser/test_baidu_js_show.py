"""Test forcing Baidu search box to be visible via JavaScript

This script tests if we can force the search box to be visible.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from playwright.sync_api import sync_playwright
import time


def test_baidu_force_visible():
    """Test forcing Baidu search box to be visible"""

    with sync_playwright() as p:
        print("Starting browser...")
        browser = p.chromium.launch(headless=False, slow_mo=1000)
        page = browser.new_page()

        print("\n1. Navigating to Baidu...")
        page.goto("https://www.baidu.com")

        print("\n2. Waiting for page load...")
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        print("\n3. Analyzing form visibility:\n")

        # Check form display
        form_info = page.evaluate("""
            () => {
                const form = document.querySelector('#form');
                if (!form) return { error: 'Form not found' };

                const style = window.getComputedStyle(form);
                return {
                    id: form.id,
                    className: form.className,
                    display: style.display,
                    visibility: style.visibility,
                    offsetParent: form.offsetParent !== null
                };
            }
        """)

        print(f"Form info: {form_info}")

        # Try different approaches to make it visible
        print("\n4. Trying different approaches:\n")

        # Approach 1: Remove display:none from form
        print("[Approach 1] Force form to be display:block")
        page.evaluate("""
            () => {
                const form = document.querySelector('#form');
                if (form) {
                    form.style.display = 'block';
                    form.style.visibility = 'visible';
                    form.style.opacity = '1';
                }
            }
        """)

        time.sleep(1)

        # Check if search box is now visible
        search_box_visible = page.evaluate("""
            () => {
                const searchBox = document.querySelector('#kw');
                return searchBox && searchBox.offsetParent !== null;
            }
        """)

        print(f"  Search box visible: {search_box_visible}")

        if search_box_visible:
            print("  -> SUCCESS! Try interacting...")

            try:
                search_box = page.locator("#kw")
                search_box.fill("广东旭诚科技有限公司")
                print("  -> Filled search box")

                search_button = page.locator("#su")
                search_button.click()
                print("  -> Clicked search button")

                time.sleep(2)
                print(f"  -> Current URL: {page.url}")

            except Exception as e:
                print(f"  -> Interaction failed: {e}")

        else:
            print("  -> Still not visible, trying approach 2...")

            # Approach 2: Check if there's a noscript fallback
            print("\n[Approach 2] Check for noscript or alternative search")
            noscript_content = page.evaluate("""
                () => {
                    const noscript = document.querySelector('noscript');
                    if (noscript) {
                        return noscript.innerHTML.substring(0, 200);
                    }
                    return null;
                }
            """)

            if noscript_content:
                print(f"  Noscript content: {noscript_content}")

            # Approach 3: Try navigating directly to search results
            print("\n[Approach 3] Navigate directly to search results")
            search_url = "https://www.baidu.com/s?wd=广东旭诚科技有限公司"
            page.goto(search_url)
            time.sleep(2)

            print(f"  -> Navigated to: {page.url}")

            # Check if search worked
            if "广东旭诚科技有限公司" in page.content() or "广东旭诚" in page.content():
                print("  -> SUCCESS: Search results found!")
            else:
                print("  -> Check page manually")

        print("\n5. Waiting 5 seconds for manual inspection...")
        time.sleep(5)

        browser.close()
        print("\nTest completed!")


if __name__ == "__main__":
    test_baidu_force_visible()
