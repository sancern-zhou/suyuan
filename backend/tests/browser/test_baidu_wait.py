"""Test Baidu search with different wait strategies

This script tests various wait strategies for Baidu search.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from playwright.sync_api import sync_playwright
import time


def test_baidu_wait_strategies():
    """Test different wait strategies for Baidu"""

    with sync_playwright() as p:
        print("Starting browser...")
        browser = p.chromium.launch(headless=False, slow_mo=500)
        page = browser.new_page()

        print("\n1. Navigating to Baidu...")
        page.goto("https://www.baidu.com")

        print("\n2. Testing different wait strategies:\n")

        # Strategy 1: Wait for networkidle
        print("[Strategy 1] Wait for networkidle")
        page.wait_for_load_state("networkidle")

        # Check if search box is visible
        search_box = page.locator("#kw")
        try:
            search_box.wait_for(state="visible", timeout=3000)
            print("  -> Search box is VISIBLE after networkidle")
        except:
            print("  -> Search box is HIDDEN after networkidle")

        # Strategy 2: Wait for specific timeout
        print("\n[Strategy 2] Wait 3 seconds")
        time.sleep(3)

        try:
            search_box.wait_for(state="visible", timeout=1000)
            print("  -> Search box is VISIBLE after 3 seconds")
        except:
            print("  -> Search box is HIDDEN after 3 seconds")

        # Strategy 3: Check page structure
        print("\n[Strategy 3] Analyzing page structure")

        # Get all input elements
        inputs = page.evaluate("""
            () => {
                const inputs = document.querySelectorAll('input');
                return Array.from(inputs).map(input => ({
                    tag: input.tagName.toLowerCase(),
                    id: input.id || '',
                    name: input.name || '',
                    class: input.className || '',
                    type: input.type || '',
                    placeholder: input.placeholder || '',
                    hidden: input.type === 'hidden',
                    styleDisplay: window.getComputedStyle(input).display,
                    styleVisibility: window.getComputedStyle(input).visibility,
                    offsetParent: input.offsetParent !== null
                }));
            }
        """)

        print(f"  -> Found {len(inputs)} input elements:")
        for i, inp in enumerate(inputs):
            if inp['id'] == 'kw' or inp['name'] == 'wd':
                print(f"     [{i}] ID={inp['id']} Name={inp['name']} Type={inp['type']}")
                print(f"         Display={inp['styleDisplay']} Visible={inp['styleVisibility']}")
                print(f"         OffsetParent={inp['offsetParent']}")

        # Strategy 4: Try using execute_js to interact
        print("\n[Strategy 4] Try direct JS interaction")

        result = page.evaluate("""
            () => {
                const input = document.querySelector('#kw');
                if (input) {
                    // Force display
                    input.style.display = 'block';
                    input.style.visibility = 'visible';

                    // Try to set value
                    input.value = '广东旭诚科技有限公司';

                    // Trigger events
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    input.dispatchEvent(new Event('change', { bubbles: true }));

                    return {
                        success: true,
                        value: input.value,
                        visible: input.offsetParent !== null
                    };
                }
                return { success: false };
            }
        """)

        print(f"  -> JS interaction result: {result}")

        # Strategy 5: Wait for body to be ready
        print("\n[Strategy 5] Wait for body.readyState")

        ready_state = page.evaluate("""
            () => {
                return {
                    readyState: document.readyState,
                    bodyDisplay: window.getComputedStyle(document.body).display,
                    bodyVisible: document.body.offsetParent !== null
                };
            }
        """)

        print(f"  -> Document readyState: {ready_state['readyState']}")

        # Check if we can find the search box by querying
        print("\n[Strategy 6] Check if we can find and interact with search box")

        try:
            # Use locator with force option
            search_box = page.locator("#kw")
            search_box.fill("广东旭诚科技有限公司", force=True)
            print("  -> Successfully filled search box with force=True")

            # Try to find and click button
            search_button = page.locator("#su")
            search_button.click(force=True)
            print("  -> Successfully clicked search button with force=True")

            time.sleep(2)

            current_url = page.url
            print(f"  -> Current URL: {current_url}")

            if "wd=" in current_url:
                print("  -> SUCCESS: Search executed!")

        except Exception as e:
            print(f"  -> FAILED: {e}")

        print("\n7. Waiting 5 seconds before closing...")
        time.sleep(5)

        browser.close()
        print("\nTest completed!")


if __name__ == "__main__":
    test_baidu_wait_strategies()
