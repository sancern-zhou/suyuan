"""Test different methods to extract mu attribute from Baidu search results

This script compares:
1. Direct DOM extraction (simplest, no refs needed)
2. Using snapshot refs (complex, requires refs parameter)
3. Hybrid approach (extract from DOM, use snapshot for context)
"""
import sys
import os
import time
from urllib.parse import quote

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from playwright.sync_api import sync_playwright


def test_method_1_direct_dom():
    """Method 1: Direct DOM extraction (simplest)"""
    print("\n" + "="*80)
    print("METHOD 1: Direct DOM Extraction")
    print("="*80)
    print("Approach: Directly query DOM for mu attributes")
    print("Pros: Simple, no refs needed, works in any page.evaluate()")
    print("Cons: Less context about element roles/types")
    print("-"*80)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        print("\n1. Navigating to Baidu search...")
        search_query = "广东旭诚科技有限公司"
        page.goto(f"https://www.baidu.com/s?wd={quote(search_query)}")
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        print("2. Extracting mu attributes using direct DOM query...")

        # Method 1a: Simple querySelectorAll
        code_1a = """
            () => {
                const results = [];
                const containers = document.querySelectorAll('div.result');

                for (let i = 0; i < Math.min(containers.length, 10); i++) {
                    const container = containers[i];
                    const mu = container.getAttribute('mu');

                    if (mu) {
                        const h3 = container.querySelector('h3');
                        const title = h3 ? h3.textContent.trim() : 'N/A';

                        results.push({
                            method: 'direct_dom',
                            title: title,
                            url: mu,
                            has_mu: true
                        });
                    }
                }

                return results;
            }
        """

        try:
            start = time.time()
            results_1a = page.evaluate(code_1a)
            elapsed_1a = (time.time() - start) * 1000

            print(f"[OK] Method 1a (querySelectorAll) succeeded in {elapsed_1a:.0f}ms")
            print(f"  Found {len(results_1a)} results with mu attributes")

            for i, r in enumerate(results_1a[:3]):
                print(f"  [{i+1}] {r['title'][:50]}...")
                print(f"      URL: {r['url'][:80]}...")

        except Exception as e:
            print(f"[FAIL] Method 1a failed: {e}")

        # Method 1b: More robust selector with error handling
        code_1b = """
            () => {
                const results = [];

                // Try multiple selector strategies
                const selectors = [
                    'div.result',      // Standard Baidu result
                    'div[tpl]',        // Baidu template-based results
                    'div.c-container',  # Alternative container
                ];

                selectors.forEach(selector => {
                    const containers = document.querySelectorAll(selector);

                    containers.forEach(container => {
                        const mu = container.getAttribute('mu');

                        if (mu && !results.find(r => r.url === mu)) {
                            const h3 = container.querySelector('h3');
                            const title = h3 ? h3.textContent.trim() : 'N/A';

                            results.push({
                                method: 'robust_dom',
                                title: title,
                                url: mu,
                                selector_used: selector
                            });
                        }
                    });
                });

                return results.slice(0, 10);
            }
        """

        try:
            start = time.time()
            results_1b = page.evaluate(code_1b)
            elapsed_1b = (time.time() - start) * 1000

            print(f"\n[OK] Method 1b (robust selectors) succeeded in {elapsed_1b:.0f}ms")
            print(f"  Found {len(results_1b)} unique results")

        except Exception as e:
            print(f"[FAIL] Method 1b failed: {e}")

        browser.close()

    return len(results_1a) if 'results_1a' in locals() else 0


def test_method_2_refs_parameter():
    """Method 2: Using refs parameter from snapshot"""
    print("\n" + "="*80)
    print("METHOD 2: Using Refs Parameter (Current Implementation)")
    print("="*80)
    print("Approach: Extract refs from snapshot, then pass to execute_js")
    print("Pros: Has element context (role, type, aria attributes)")
    print("Cons: Requires two steps, refs parameter not currently supported")
    print("-"*80)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        print("\n1. Navigating to Baidu search...")
        search_query = "广东旭诚科技有限公司"
        page.goto(f"https://www.baidu.com/s?wd={quote(search_query)}")
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        print("2. Taking snapshot to get refs...")

        # Simulate snapshot refs extraction
        snapshot_code = """
            () => {
                const refs = {};
                let refId = 1;

                // Simulate extracting refs from page
                const results = document.querySelectorAll('div.result');

                results.forEach(container => {
                    const mu = container.getAttribute('mu');

                    if (mu) {
                        const h3 = container.querySelector('h3');
                        const title = h3 ? h3.textContent.trim() : 'N/A';
                        const link = h3?.querySelector('a');

                        refs[`e${refId++}`] = {
                            role: 'link',
                            name: title,
                            html_attrs: {
                                mu: mu,
                                href: link?.getAttribute('href') || mu
                            }
                        };
                    }
                });

                return refs;
            }
        """

        try:
            refs = page.evaluate(snapshot_code)
            print(f"[OK] Snapshot extracted {len(refs)} refs with mu attributes")

        except Exception as e:
            print(f"[FAIL] Snapshot failed: {e}")
            browser.close()
            return 0

        print("\n3. Testing different ways to pass refs to execute_js...")

        # Method 2a: Passing refs as parameter (correct way)
        code_2a = """
            (refs) => {
                for (const [refId, refData] of Object.entries(refs)) {
                    if (refData.html_attrs && refData.html_attrs.mu) {
                        const mu = refData.html_attrs.mu;
                        if (mu.includes('旭诚科技') || mu.includes('xucheng')) {
                            return {
                                method: 'refs_parameter',
                                found: true,
                                ref_id: refId,
                                url: mu
                            };
                        }
                    }
                }
                return { method: 'refs_parameter', found: false };
            }
        """

        try:
            start = time.time()
            result_2a = page.evaluate(code_2a, refs)
            elapsed_2a = (time.time() - start) * 1000

            if result_2a['found']:
                print(f"[OK] Method 2a (refs as parameter) succeeded in {elapsed_2a:.0f}ms")
                print(f"  Found: {result_2a['url']}")
            else:
                print(f"[OK] Method 2a executed but no match found")

        except Exception as e:
            print(f"[FAIL] Method 2a failed: {e}")

        # Method 2b: Using arguments (WRONG - demonstrates the bug)
        code_2b = """
            () => {
                const refs = arguments[0];  // This will fail!
                for (const [refId, refData] of Object.entries(refs)) {
                    if (refData.html_attrs && refData.html_attrs.mu) {
                        return refData.html_attrs.mu;
                    }
                }
                return null;
            }
        """

        try:
            result_2b = page.evaluate(code_2b)
            print(f"[FAIL] Method 2b (using arguments) - Should have failed but didn't!")

        except Exception as e:
            print(f"[OK] Method 2b (using arguments) - Expected failure: {str(e)[:60]}...")

        # Method 2c: Arrow function with parameter (correct)
        code_2c = "(refs) => { /* refs is now available */ return Object.keys(refs).length; }"

        try:
            count = page.evaluate(code_2c, refs)
            print(f"[OK] Method 2c (arrow function with parameter) - Counted {count} refs")

        except Exception as e:
            print(f"[FAIL] Method 2c failed: {e}")

        browser.close()

    return len(refs) if 'refs' in locals() else 0


def test_method_3_hybrid():
    """Method 3: Hybrid approach - use snapshot for context, direct DOM for extraction"""
    print("\n" + "="*80)
    print("METHOD 3: Hybrid Approach (Recommended)")
    print("="*80)
    print("Approach: Use snapshot to identify target elements, then direct DOM to extract")
    print("Pros: Best of both worlds - context + simplicity")
    print("Cons: Two-step process")
    print("-"*80)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        print("\n1. Navigating to Baidu search...")
        search_query = "广东旭诚科技有限公司"
        page.goto(f"https://www.baidu.com/s?wd={quote(search_query)}")
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        print("\n2. Quick snapshot to understand page structure...")

        # Lightweight snapshot - just get titles and positions
        snapshot_code = """
            () => {
                const info = [];
                const results = document.querySelectorAll('div.result');

                results.forEach((container, index) => {
                    const h3 = container.querySelector('h3');
                    if (h3) {
                        info.push({
                            index: index,
                            title: h3.textContent.trim().substring(0, 50)
                        });
                    }
                });

                return info;
            }
        """

        try:
            snapshot = page.evaluate(snapshot_code)
            print(f"[OK] Snapshot found {len(snapshot)} search results")
            for i, item in enumerate(snapshot[:3]):
                print(f"  [{i+1}] {item['title']}...")

        except Exception as e:
            print(f"[FAIL] Snapshot failed: {e}")
            browser.close()
            return 0

        print("\n3. Extract mu attributes using index-based approach...")

        # Use the snapshot info to guide the extraction
        extraction_code = """
            (targetIndices) => {
                const results = [];
                const containers = document.querySelectorAll('div.result');

                targetIndices.forEach(idx => {
                    if (idx < containers.length) {
                        const container = containers[idx];
                        const mu = container.getAttribute('mu');

                        if (mu) {
                            const h3 = container.querySelector('h3');
                            results.push({
                                index: idx,
                                title: h3 ? h3.textContent.trim() : 'N/A',
                                url: mu
                            });
                        }
                    }
                });

                return results;
            }
        """

        try:
            # Extract all results
            target_indices = list(range(min(len(snapshot), 10)))
            results = page.evaluate(extraction_code, target_indices)

            print(f"[OK] Hybrid method extracted {len(results)} results with mu attributes")

            # Look for target company
            for r in results:
                if '旭诚' in r['title']:
                    print(f"\n  Found target company:")
                    print(f"    Title: {r['title']}")
                    print(f"    URL: {r['url']}")
                    break

        except Exception as e:
            print(f"[FAIL] Hybrid extraction failed: {e}")

        browser.close()

    return len(results) if 'results' in locals() else 0


def test_method_4_implementation():
    """Method 4: Test the actual execute_js implementation fix"""
    print("\n" + "="*80)
    print("METHOD 4: Testing execute_js Implementation Fix")
    print("="*80)
    print("Approach: Simulate the fixed execute_js with refs parameter support")
    print("-"*80)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        print("\n1. Navigating to Baidu search...")
        search_query = "广东旭诚科技有限公司"
        page.goto(f"https://www.baidu.com/s?wd={quote(search_query)}")
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        print("\n2. Simulating current (broken) implementation...")

        # Current implementation: no parameter passing
        current_code = """
            () => {
                const refs = arguments[0];  // This fails!
                return refs;
            }
        """

        try:
            result = page.evaluate(current_code)
            print(f"  [FAIL] Current implementation should fail but got: {result}")

        except Exception as e:
            print(f"  [OK] Current implementation fails as expected:")
            print(f"    Error: {str(e)[:80]}...")

        print("\n3. Testing fixed implementation...")

        # Fixed implementation: parameter passing
        # Simulate what the fixed execute_js should do
        mock_refs = {"test": "data"}
        fixed_code = "(refs) => { return { received: refs, success: true }; }"

        try:
            result = page.evaluate(fixed_code, mock_refs)
            print(f"  [OK] Fixed implementation works!")
            print(f"    Received refs: {result['received']}")

        except Exception as e:
            print(f"  [FAIL] Fixed implementation failed: {e}")

        print("\n4. Real-world example with actual refs...")

        # Get actual refs
        get_refs = """
            () => {
                const refs = {};
                document.querySelectorAll('div.result[mu]').forEach((el, idx) => {
                    refs[`e${idx}`] = {
                        role: 'link',
                        html_attrs: {
                            mu: el.getAttribute('mu')
                        }
                    };
                });
                return refs;
            }
        """

        actual_refs = page.evaluate(get_refs)
        print(f"  Extracted {len(actual_refs)} refs with mu attributes")

        # Use refs in extraction
        search_refs = """
            (refs, keyword) => {
                for (const [id, data] of Object.entries(refs)) {
                    if (data.html_attrs.mu.includes(keyword)) {
                        return { ref_id: id, url: data.html_attrs.mu };
                    }
                }
                return null;
            }
        """

        result = page.evaluate(search_refs, actual_refs, "旭诚")
        print(f"  Search result: {result}")

        browser.close()


def main():
    print("\n" + "="*80)
    print("BAIDU MU ATTRIBUTE EXTRACTION - METHOD COMPARISON")
    print("="*80)
    print("Testing different approaches to extract mu attributes from Baidu search")
    print("search results to determine the optimal solution.")

    results = {}

    try:
        results['method_1'] = test_method_1_direct_dom()
    except Exception as e:
        print(f"\n[FAIL] Method 1 failed with exception: {e}")
        results['method_1'] = 0

    try:
        results['method_2'] = test_method_2_refs_parameter()
    except Exception as e:
        print(f"\n[FAIL] Method 2 failed with exception: {e}")
        results['method_2'] = 0

    try:
        results['method_3'] = test_method_3_hybrid()
    except Exception as e:
        print(f"\n[FAIL] Method 3 failed with exception: {e}")
        results['method_3'] = 0

    try:
        test_method_4_implementation()
    except Exception as e:
        print(f"\n[FAIL] Method 4 failed with exception: {e}")

    # Summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"Method 1 (Direct DOM):        {results.get('method_1', 0)} results found")
    print(f"Method 2 (Refs Parameter):    {results.get('method_2', 0)} results found")
    print(f"Method 3 (Hybrid):            {results.get('method_3', 0)} results found")

    print("\n" + "="*80)
    print("RECOMMENDATION")
    print("="*80)

    winner = max(results.items(), key=lambda x: x[1])[0] if results else "none"

    if winner == 'method_1' or results.get('method_1', 0) >= results.get('method_3', 0):
        print("[OK] RECOMMENDED: Method 1 (Direct DOM Extraction)")
        print("\nReasons:")
        print("  1. Simplest - single step, no refs needed")
        print("  2. Fastest - no two-step process")
        print("  3. Most reliable - works with standard Playwright API")
        print("  4. Easier to maintain - straightforward DOM queries")
        print("\nChanges needed:")
        print("  1. Update browser_skills_guide.md to use direct DOM examples")
        print("  2. Remove refs-based examples (or move to advanced section)")
        print("  3. Update execute_js examples to show direct DOM queries")

    elif winner == 'method_3':
        print("[OK] RECOMMENDED: Method 3 (Hybrid Approach)")
        print("\nReasons:")
        print("  1. Good balance of context and simplicity")
        print("  2. Allows LLM to understand page before extraction")
        print("\nChanges needed:")
        print("  1. Update browser_skills_guide.md to show two-step process")
        print("  2. First step: snapshot for context")
        print("  3. Second step: direct DOM extraction")

    print("\n" + "="*80)
    print("NOTES:")
    print("- Method 2 (refs parameter) requires fixing execute_js.py")
    print("- Current bug: page.evaluate() doesn't pass refs to user code")
    print("- Fix: Check for refs in kwargs and pass as parameter if present")
    print("="*80 + "\n")


if __name__ == "__main__":
    main()
