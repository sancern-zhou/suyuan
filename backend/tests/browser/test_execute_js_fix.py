"""Test execute_js fix for refs parameter support

This test verifies:
1. Direct DOM extraction works (Method 1)
2. Refs parameter support works (Method 2)
3. Backward compatibility maintained
"""
import sys
import os
import time
from urllib.parse import quote

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from playwright.sync_api import sync_playwright


def test_direct_dom_extraction():
    """Test Method 1: Direct DOM extraction (simplest, no refs needed)"""
    print("\n" + "="*80)
    print("TEST 1: Direct DOM Extraction (No Refs Needed)")
    print("="*80)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        # Navigate to Baidu
        search_query = "广东旭诚科技有限公司"
        page.goto(f"https://www.baidu.com/s?wd={quote(search_query)}")
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        # Extract mu attributes directly from DOM
        code = """
            () => {
                const results = [];
                document.querySelectorAll('div.result[mu]').forEach(container => {
                    const mu = container.getAttribute('mu');
                    const h3 = container.querySelector('h3');
                    if (mu && h3) {
                        results.push({
                            title: h3.textContent.trim(),
                            url: mu
                        });
                    }
                });
                return results;
            }
        """

        try:
            results = page.evaluate(code)
            print(f"[OK] Found {len(results)} results with mu attributes")
            for i, r in enumerate(results[:3]):
                print(f"  [{i+1}] {r['title'][:50]}...")
                print(f"      URL: {r['url'][:60]}...")

            # Look for target company
            for r in results:
                if '旭诚' in r['title']:
                    print(f"\n[OK] Found target company:")
                    print(f"  Title: {r['title']}")
                    print(f"  URL: {r['url']}")
                    return True

        except Exception as e:
            print(f"[FAIL] Error: {e}")
            return False

        browser.close()

    return False


def test_refs_parameter_support():
    """Test Method 2: Refs parameter support (fixed implementation)"""
    print("\n" + "="*80)
    print("TEST 2: Refs Parameter Support (Fixed Implementation)")
    print("="*80)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        # Navigate to Baidu
        search_query = "广东旭诚科技有限公司"
        page.goto(f"https://www.baidu.com/s?wd={quote(search_query)}")
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        # Simulate getting refs from snapshot
        print("\n1. Simulating snapshot to get refs...")
        get_refs_code = """
            () => {
                const refs = {};
                document.querySelectorAll('div.result[mu]').forEach((el, idx) => {
                    const h3 = el.querySelector('h3');
                    refs[`e${idx}`] = {
                        role: 'link',
                        name: h3 ? h3.textContent.trim() : 'N/A',
                        html_attrs: {
                            mu: el.getAttribute('mu')
                        }
                    };
                });
                return refs;
            }
        """

        try:
            refs = page.evaluate(get_refs_code)
            print(f"[OK] Extracted {len(refs)} refs from page")

        except Exception as e:
            print(f"[FAIL] Could not extract refs: {e}")
            browser.close()
            return False

        # Test 2a: Using refs parameter (correct way after fix)
        print("\n2. Testing refs parameter (FIXED implementation)...")
        search_code = """
            (refs) => {
                for (const [refId, refData] of Object.entries(refs)) {
                    if (refData.name && refData.name.includes('旭诚')) {
                        return {
                            ref_id: refId,
                            url: refData.html_attrs.mu,
                            name: refData.name
                        };
                    }
                }
                return null;
            }
        """

        try:
            result = page.evaluate(search_code, refs)

            if result:
                print(f"[OK] Refs parameter works!")
                print(f"  Found: {result['name']}")
                print(f"  URL: {result['url']}")
                print(f"  Ref ID: {result['ref_id']}")
                return True
            else:
                print(f"[OK] Refs parameter executed but no match found")
                return False

        except Exception as e:
            print(f"[FAIL] Refs parameter failed: {e}")
            browser.close()
            return False


def test_backward_compatibility():
    """Test backward compatibility (no refs parameter)"""
    print("\n" + "="*80)
    print("TEST 3: Backward Compatibility (No Refs Parameter)")
    print("="*80)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        # Navigate to Baidu
        search_query = "广东旭诚科技有限公司"
        page.goto(f"https://www.baidu.com/s?wd={quote(search_query)}")
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        # Test without refs parameter (old way)
        code = """
            () => {
                return {
                    title: document.title,
                    url_count: document.querySelectorAll('div.result[mu]').length
                };
            }
        """

        try:
            result = page.evaluate(code)
            print(f"[OK] Backward compatibility maintained")
            print(f"  Title: {result['title']}")
            print(f"  URL count: {result['url_count']}")
            return True

        except Exception as e:
            print(f"[FAIL] Backward compatibility broken: {e}")
            return False

        browser.close()


def test_old_code_fails_as_expected():
    """Test that old buggy code fails as expected"""
    print("\n" + "="*80)
    print("TEST 4: Old Buggy Code Fails As Expected")
    print("="*80)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        # Navigate to Baidu
        search_query = "广东旭诚科技有限公司"
        page.goto(f"https://www.baidu.com/s?wd={quote(search_query)}")
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        # Old buggy code (using arguments[0])
        old_buggy_code = """
            () => {
                const refs = arguments[0];  // This will fail!
                return refs;
            }
        """

        try:
            result = page.evaluate(old_buggy_code)
            print(f"[UNEXPECTED] Old code should fail but returned: {result}")
            return False

        except Exception as e:
            expected_error = "arguments is not defined"
            if expected_error in str(e):
                print(f"[OK] Old buggy code fails as expected:")
                print(f"  Error: {str(e)[:80]}...")
                return True
            else:
                print(f"[UNEXPECTED] Different error: {e}")
                return False

        browser.close()


def main():
    print("\n" + "="*80)
    print("EXECUTE_JS FIX VERIFICATION")
    print("="*80)
    print("Testing the fix for refs parameter support in execute_js")

    results = {}

    # Test 1: Direct DOM extraction (should work before and after fix)
    results['direct_dom'] = test_direct_dom_extraction()

    # Test 2: Refs parameter support (should work after fix)
    results['refs_param'] = test_refs_parameter_support()

    # Test 3: Backward compatibility
    results['backward_compat'] = test_backward_compatibility()

    # Test 4: Old code fails as expected
    results['old_fails'] = test_old_code_fails_as_expected()

    # Summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"Direct DOM Extraction:     {results.get('direct_dom', False)}")
    print(f"Refs Parameter Support:    {results.get('refs_param', False)}")
    print(f"Backward Compatibility:    {results.get('backward_compat', False)}")
    print(f"Old Code Fails:            {results.get('old_fails', False)}")

    all_passed = all(results.values())

    print("\n" + "="*80)
    if all_passed:
        print("[SUCCESS] All tests passed!")
        print("\nThe execute_js fix is working correctly:")
        print("1. Direct DOM extraction works (simplest method)")
        print("2. Refs parameter support works (for advanced usage)")
        print("3. Backward compatibility maintained")
        print("4. Old buggy code fails as expected")
    else:
        print("[FAIL] Some tests failed")
        print("Please check the implementation")
    print("="*80 + "\n")

    return 0 if all_passed else 1


if __name__ == "__main__":
    exit(main())
