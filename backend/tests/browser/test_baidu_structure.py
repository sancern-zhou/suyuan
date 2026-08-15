"""Analyze Baidu page structure to find why search box is hidden

This script analyzes the DOM structure to understand the hidden container issue.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from playwright.sync_api import sync_playwright
import time


def test_baidu_structure():
    """Analyze Baidu page structure"""

    with sync_playwright() as p:
        print("Starting browser...")
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        print("\n1. Navigating to Baidu...")
        page.goto("https://www.baidu.com")

        print("\n2. Waiting for page load...")
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        print("\n3. Analyzing search box container structure:\n")

        # Analyze the parent hierarchy of #kw
        structure = page.evaluate("""
            () => {
                const searchBox = document.querySelector('#kw');
                if (!searchBox) return { error: 'Search box not found' };

                const parents = [];
                let current = searchBox;

                while (current && current !== document.body) {
                    const style = window.getComputedStyle(current);
                    parents.push({
                        tag: current.tagName.toLowerCase(),
                        id: current.id || '',
                        class: current.className || '',
                        display: style.display,
                        visibility: style.visibility,
                        opacity: style.opacity,
                        offsetParent: current.offsetParent !== null,
                        rect: current.getBoundingClientRect().toString()
                    });

                    current = current.parentElement;
                }

                return {
                    searchBox: {
                        id: searchBox.id,
                        name: searchBox.name,
                        display: window.getComputedStyle(searchBox).display,
                        offsetParent: searchBox.offsetParent !== null,
                        rect: searchBox.getBoundingClientRect().toString()
                    },
                    parents: parents
                };
            }
        """)

        print(f"Search box info:")
        print(f"  ID: {structure['searchBox']['id']}")
        print(f"  Name: {structure['searchBox']['name']}")
        print(f"  Display: {structure['searchBox']['display']}")
        print(f"  OffsetParent: {structure['searchBox']['offsetParent']}")
        print(f"  Rect: {structure['searchBox']['rect']}")

        print(f"\nParent hierarchy (search box -> body):")
        for i, parent in enumerate(structure['parents']):
            visible = "VISIBLE" if parent['offsetParent'] else "HIDDEN"
            print(f"  [{i}] {parent['tag']}", end="")
            if parent['id']:
                print(f"#{parent['id']}", end="")
            if parent['class']:
                class_str = parent['class'][:30] if len(parent['class']) > 30 else parent['class']
                print(f".{class_str}", end="")
            print(f" [{visible}]")
            print(f"      Display: {parent['display']}, Visibility: {parent['visibility']}, Opacity: {parent['opacity']}")

        print("\n4. Checking for wrapper elements that might be hidden:\n")

        # Find hidden containers
        hidden_containers = page.evaluate("""
            () => {
                const containers = [];

                // Check common wrapper selectors
                const selectors = ['#wrapper', '#head', '.s_form', '#s_form_wrapper'];

                selectors.forEach(selector => {
                    const el = document.querySelector(selector);
                    if (el) {
                        const style = window.getComputedStyle(el);
                        containers.push({
                            selector: selector,
                            display: style.display,
                            visibility: style.visibility,
                            opacity: style.opacity,
                            offsetParent: el.offsetParent !== null
                        });
                    }
                });

                return containers;
            }
        """)

        for container in hidden_containers:
            visible = "VISIBLE" if container['offsetParent'] else "HIDDEN"
            print(f"  {container['selector']}: [{visible}]")
            print(f"    Display: {container['display']}, Visibility: {container['visibility']}")

        print("\n5. Trying to make search box visible:\n")

        # Try to make the search box visible by unhiding parents
        result = page.evaluate("""
            () => {
                const searchBox = document.querySelector('#kw');
                if (!searchBox) return { success: false, error: 'Search box not found' };

                // Force all parents to be visible
                let current = searchBox;
                while (current && current !== document.body) {
                    current.style.display = '';
                    current.style.visibility = 'visible';
                    current.style.opacity = '1';
                    current = current.parentElement;
                }

                // Check if it's now visible
                return {
                    success: true,
                    offsetParent: searchBox.offsetParent !== null,
                    rect: searchBox.getBoundingClientRect().toString()
                };
            }
        """)

        print(f"  Result: {result}")

        if result['offsetParent']:
            print("  -> SUCCESS: Search box is now visible!")

            # Try to interact
            try:
                search_box = page.locator("#kw")
                search_box.fill("广东旭诚科技有限公司")
                print("  -> Successfully filled search box")

                search_button = page.locator("#su")
                search_button.click()
                print("  -> Successfully clicked search button")

                time.sleep(2)
                print(f"  -> Current URL: {page.url}")

            except Exception as e:
                print(f"  -> Interaction failed: {e}")
        else:
            print("  -> FAILED: Search box still not visible")

        print("\n6. Waiting 3 seconds before closing...")
        time.sleep(3)

        browser.close()
        print("\nTest completed!")


if __name__ == "__main__":
    test_baidu_structure()
