# -*- coding: utf-8 -*-
"""
简化版自动化测试 - 更健壮
"""
import asyncio
import json
from playwright.async_api import async_playwright
from datetime import datetime

BASE_URL = "http://10.10.10.158"
USERNAME = "cdzhuanyong"
PASSWORD = "cdsz@429"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=500)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            ignore_https_errors=True
        )
        page = await context.new_page()

        print("=" * 70)
        print("  Start Auto Test")
        print("=" * 70)

        try:
            # Step 1: Login
            print("\n[1] Login...")
            await page.goto(BASE_URL, timeout=30000)
            await page.wait_for_timeout(1000)

            # Use JavaScript to fill and click
            await page.evaluate(f"""
                () => {{
                    const inputs = document.querySelectorAll('input[type="text"], input[type="username"]');
                    if (inputs.length > 0) inputs[0].value = '{USERNAME}';

                    const passwords = document.querySelectorAll('input[type="password"]');
                    if (passwords.length > 0) passwords[0].value = '{PASSWORD}';

                    const buttons = document.querySelectorAll('button');
                    for (const btn of buttons) {{
                        if (btn.textContent.includes('login') || btn.textContent.includes('Login')) {{
                            btn.click();
                            return true;
                        }}
                    }}
                    return false;
                }}
            """)

            await page.wait_for_timeout(3000)
            print("OK - Logged in")

            # Step 2: Click real-time preview
            print("\n[2] Click preview...")
            await page.evaluate("""
                () => {
                    const all = document.querySelectorAll('*');
                    for (const el of all) {
                        if (el.textContent.includes('实时预览')) {
                            el.click();
                            return true;
                        }
                    }
                    return false;
                }
            """)

            await page.wait_for_timeout(8000)  # Increased wait time
            await page.screenshot(path="test_01_after_preview.png")
            print("OK - Preview clicked")

            # Step 3: Get iframe
            print("\n[3] Get iframe...")

            # Wait for iframe to appear
            await page.wait_for_timeout(5000)

            # Debug: Print page URL and title
            current_url = page.url
            page_title = await page.title()
            print(f"  Current URL: {current_url}")
            print(f"  Page title: {page_title}")

            iframe = page.frame(name="vms_010100")
            if not iframe:
                # Try to find iframe by other means
                print("  Trying to find iframe...")
                iframe_elements = await page.query_selector_all("iframe")
                print(f"  Found {len(iframe_elements)} iframes")

                if len(iframe_elements) == 0:
                    print("  ERROR - No iframes found on page!")
                    print("  Saving page source for debug...")
                    page_content = await page.content()
                    with open("debug_page_source.html", "w", encoding="utf-8") as f:
                        f.write(page_content)
                    print("  Saved to: debug_page_source.html")
                    await page.wait_for_timeout(30000)
                    return

                for idx, iframe_el in enumerate(iframe_elements):
                    name = await iframe_el.get_attribute("name")
                    src = await iframe_el.get_attribute("src")
                    id_attr = await iframe_el.get_attribute("id")
                    print(f"  [{idx}] name={name}, id={id_attr}, src={src}")

                    if name == "vms_010100" or (src and "vms" in src):
                        try:
                            iframe = await iframe_el.content_frame()
                            print(f"  Got iframe from element [{idx}]")
                            break
                        except Exception as e:
                            print(f"  Error getting content frame: {e}")

            if not iframe:
                print("ERROR - Cannot get iframe")
                print("\nKeeping browser open for 30 seconds for manual inspection...")
                await page.wait_for_timeout(30000)
                return

            print("OK - iframe obtained")
            await page.wait_for_timeout(3000)

            # Step 4: List all elements in iframe
            print("\n[4] Analyze iframe content...")

            try:
                all_info = await iframe.evaluate("""
                    () => {
                        return {
                            title: document.title,
                            url: window.location.href,
                            totalElements: document.querySelectorAll('*').length,
                            bodyText: document.body.textContent.substring(0, 500)
                        };
                    }
                """)

                print(f"  Title: {all_info['title']}")
                print(f"  URL: {all_info['url']}")
                print(f"  Total elements: {all_info['totalElements']}")
                print(f"  Body text preview: {all_info['bodyText'][:200]}")

            except Exception as e:
                print(f"ERROR getting iframe info: {e}")

            # Step 5: Find all clickable elements
            print("\n[5] Find all clickable elements...")

            try:
                clickable = await iframe.evaluate("""
                    () => {
                        const results = [];
                        const all = document.querySelectorAll('*');

                        all.forEach(el => {
                            const rect = el.getBoundingClientRect();
                            const text = (el.textContent || '').trim();

                            if (rect.x < 300 && rect.width > 0 && rect.height > 0) {
                                if (text && text.length > 0 && text.length < 100) {
                                    const hasClick = el.onclick !== null ||
                                        el.style.cursor === 'pointer' ||
                                        /icon|button|menu|item|nav/i.test(el.className || '');

                                    if (hasClick || text.length < 50) {
                                        results.push({
                                            tag: el.tagName,
                                            text: text,
                                            class: el.className,
                                            x: Math.round(rect.x),
                                            y: Math.round(rect.y),
                                            hasClick: hasClick
                                        });
                                    }
                                }
                            }
                        });

                        return results.slice(0, 50);
                    }
                """)

                print(f"  Found {len(clickable)} elements:")
                for idx, el in enumerate(clickable[:30]):
                    click_mark = " [CLICK]" if el['hasClick'] else ""
                    print(f"    [{idx:2d}] <{el['tag']:4s}> ({el['x']:3d}, {el['y']:3d}) '{el['text'][:30]}'{click_mark}")

                # Save to file
                with open("clickable_elements.json", "w", encoding="utf-8") as f:
                    json.dump(clickable, f, ensure_ascii=False, indent=2)
                print("\n  Saved to: clickable_elements.json")

            except Exception as e:
                print(f"ERROR finding elements: {e}")

            # Step 6: Try to expand menu
            print("\n[6] Try to expand menu...")

            strategies = [
                "Click li.el-menu--colloase-btn",
                "Click (20, 20)",
                "Click (30, 30)",
            ]

            for strategy in strategies:
                print(f"  Trying: {strategy}")

                try:
                    if "colloase" in strategy:
                        result = await iframe.evaluate("""
                            () => {
                                const el = document.querySelector('li.el-menu--colloase-btn');
                                if (el) {
                                    el.click();
                                    return true;
                                }
                                return false;
                            }
                        """)
                        if result:
                            print("  OK - Clicked")
                            await page.wait_for_timeout(2000)
                            await page.screenshot(path="test_02_menu_expanded.png")
                            break

                    elif "(20, 20)" in strategy:
                        await page.mouse.click(20, 20)
                        await page.wait_for_timeout(2000)
                        await page.screenshot(path="test_03_click_20_20.png")

                    elif "(30, 30)" in strategy:
                        await page.mouse.click(30, 30)
                        await page.wait_for_timeout(2000)
                        await page.screenshot(path="test_04_click_30_30.png")

                except Exception as e:
                    print(f"  Failed: {e}")

            # Step 7: Final screenshot
            print("\n[7] Final analysis...")
            await page.screenshot(path="test_final.png", full_page=True)

            print("\n" + "=" * 70)
            print("  Test Complete!")
            print("=" * 70)
            print("\nGenerated files:")
            print("  - test_01_after_preview.png")
            print("  - test_02_menu_expanded.png")
            print("  - clickable_elements.json")
            print("  - test_final.png")

            print("\nBrowser will stay open for 30 seconds...")
            await page.wait_for_timeout(30000)

        except Exception as e:
            print(f"\nERROR: {e}")
            import traceback
            traceback.print_exc()
            await page.screenshot(path="error.png")

        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
