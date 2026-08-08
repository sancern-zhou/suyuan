"""Test Baidu search functionality

This script tests various selectors to find the correct way to interact with Baidu.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from playwright.sync_api import sync_playwright
import time


def test_baidu_selectors():
    """Test different selectors for Baidu search box"""

    with sync_playwright() as p:
        print("Starting browser...")
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        print("\n1. Navigating to Baidu...")
        page.goto("https://www.baidu.com")

        print("2. Waiting for page to fully load...")
        page.wait_for_load_state("networkidle")
        time.sleep(2)  # Extra wait for dynamic content

        print("\n3. Testing different selectors:\n")

        # Test different selectors
        selectors_to_test = [
            ("ID selector", "#kw"),
            ("Name selector", "input[name='wd']"),
            ("ID attribute", "[id='kw']"),
            ("Name attribute", "[name='wd']"),
            ("Combined", "#kw[name='wd']"),
            ("Placeholder", "input[placeholder*='百度']"),
            ("Class name", ".s_ipt"),
        ]

        found_selectors = []

        for name, selector in selectors_to_test:
            try:
                # Try to wait for element with longer timeout
                element = page.wait_for_selector(selector, timeout=5000, state="visible")
                if element:
                    print(f"[OK] {name:20} | {selector:30} | FOUND")
                    found_selectors.append((name, selector))

                    # Get element details
                    attrs = element.evaluate("""
                        el => {
                            return {
                                tag: el.tagName.toLowerCase(),
                                id: el.id || '',
                                name: el.name || '',
                                class: el.className || '',
                                placeholder: el.placeholder || '',
                                type: el.type || '',
                                visible: el.offsetParent !== null
                            }
                        }
                    """)
                    print(f"  -> Tag: {attrs['tag']}, ID: '{attrs['id']}', Name: '{attrs['name']}'")
                    print(f"  -> Class: '{attrs['class']}', Placeholder: '{attrs['placeholder']}'")
                    print(f"  -> Type: {attrs['type']}, Visible: {attrs['visible']}")
            except Exception as e:
                error_msg = str(e)
                if "hidden" in error_msg:
                    print(f"[HIDDEN] {name:20} | {selector:30} | Element found but hidden")
                else:
                    print(f"[FAIL] {name:20} | {selector:30} | {error_msg[:50]}")

        print(f"\n4. Found {len(found_selectors)} working selectors")

        # Test button selectors
        print("\n5. Testing search button selectors:\n")

        button_selectors = [
            ("ID selector", "#su"),
            ("Class selector", ".s_btn"),
            ("Type attribute", "input[type='submit']"),
        ]

        for name, selector in button_selectors:
            try:
                element = page.wait_for_selector(selector, timeout=3000, state="visible")
                if element:
                    print(f"[OK] {name:20} | {selector:30} | FOUND")
            except Exception as e:
                print(f"[FAIL] {name:20} | {selector:30} | NOT FOUND")

        # Test actual interaction
        if found_selectors:
            print(f"\n6. Testing interaction with: {found_selectors[0][1]}")

            try:
                search_box = page.locator(found_selectors[0][1])

                # Wait for element to be ready
                search_box.wait_for(state="visible", timeout=5000)

                search_box.fill("广东旭诚科技有限公司")
                print("[OK] Text entered successfully")

                time.sleep(1)

                # Try clicking search button
                search_button = page.locator("#su")
                search_button.wait_for(state="visible", timeout=5000)
                search_button.click()
                print("[OK] Search button clicked")

                time.sleep(2)

                # Check if we navigated to search results
                current_url = page.url
                if "s.baidu.com" in current_url or "wd=" in current_url:
                    print(f"[OK] Search successful! URL: {current_url}")
                else:
                    print(f"[?] Current URL: {current_url}")

            except Exception as e:
                print(f"[FAIL] Interaction failed: {e}")

        print("\n7. Waiting 3 seconds before closing...")
        time.sleep(3)

        browser.close()
        print("\nTest completed!")


if __name__ == "__main__":
    test_baidu_selectors()
