# -*- coding: utf-8 -*-
"""
Simple Recording Tool - Records your manual operations

Usage:
1. Run this script
2. Manually login in the browser (60 seconds provided)
3. Perform your operations (click realtime preview, expand menu, click resource view, etc.)
4. Press Ctrl+C to end recording
5. Check recorded_actions.json for the results
"""

import asyncio
import json
from datetime import datetime
from playwright.async_api import async_playwright

BASE_URL = "http://10.10.10.158"

async def main():
    print("=" * 70)
    print("  Simple Recording Tool")
    print("=" * 70)
    print()
    print("Starting browser...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            slow_mo=300,
            args=['--ignore-certificate-errors', '--start-maximized']
        )

        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            ignore_https_errors=True
        )

        page = await context.new_page()

        # Store all actions
        all_actions = []

        # Console listener
        def handle_console(msg):
            if msg.type == "log":
                text = msg.text
                if text.startswith("ACTION:"):
                    try:
                        parts = text.split(":", 2)
                        if len(parts) >= 3:
                            action_data = json.loads(parts[2])
                            all_actions.append({
                                "type": parts[1],
                                "details": action_data,
                                "timestamp": datetime.now().isoformat()
                            })
                            print(f"[Record] {parts[1]}: {action_data.get('text', '')[:40]}")
                    except:
                        pass
                elif text == "RECORDER_READY":
                    print("\n[Recording] Recorder is ready!\n")

        page.on("console", handle_console)

        # Navigate to page
        print("Opening page...")
        await page.goto(BASE_URL)

        print("\n" + "=" * 70)
        print("  Browser Ready")
        print("=" * 70)
        print("\nPlease login manually:")
        print("  Username: cdzhuanyong")
        print("  Password: cdsz@429")
        print("\nWaiting 60 seconds for you to login...")
        print("Recording will start automatically after login.\n")

        # Wait for manual login
        await page.wait_for_timeout(60000)

        # Inject recorder
        print("\n[Recording] Injecting recorder...")
        await page.evaluate("""
            () => {
                document.addEventListener('click', (e) => {
                    const target = e.target;
                    const rect = target.getBoundingClientRect();

                    if (rect.width > 0 && rect.height > 0 && rect.width < 500 && rect.height < 500) {
                        const info = {
                            tagName: target.tagName,
                            id: target.id || '',
                            className: target.className || '',
                            text: (target.textContent || '').trim().substring(0, 80),
                            x: Math.round(rect.x),
                            y: Math.round(rect.y),
                            width: Math.round(rect.width),
                            height: Math.round(rect.height),
                            role: target.getAttribute('role') || '',
                            ariaLabel: target.getAttribute('aria-label') || '',
                            title: target.getAttribute('title') || '',
                            onclick: target.onclick !== null
                        };

                        console.log('ACTION:CLICK:' + JSON.stringify(info));
                    }
                }, true);

                console.log('RECORDER_READY');
            }
        """)

        await page.wait_for_timeout(1000)

        print("\n" + "=" * 70)
        print("  Recording Started")
        print("=" * 70)
        print("\nPlease perform your operations:")
        print("\n1. Click 'Realtime Preview' (实时预览)")
        print("2. Wait for page to load")
        print("3. Expand left menu if needed")
        print("4. Click 'Resource View' (资源视图)")
        print("5. Expand 'Monitor Points' (监控点)")
        print("6. Expand 'Root Node' (根节点) if exists")
        print("7. Click specific station")
        print("8. Open video monitoring")
        print("\nPress Ctrl+C when done.\n")
        print("=" * 70)
        print()

        try:
            # Keep browser open for 5 minutes
            await page.wait_for_timeout(300000)

        except KeyboardInterrupt:
            print("\n" + "=" * 70)
            print("  Recording Ended")
            print("=" * 70)
            print(f"\nTotal actions recorded: {len(all_actions)}\n")

            # Save to file
            with open("recorded_actions.json", "w", encoding="utf-8") as f:
                json.dump(all_actions, f, ensure_ascii=False, indent=2)

            print("Actions saved to: recorded_actions.json\n")

            # Display all actions
            for idx, action in enumerate(all_actions):
                print(f"{idx + 1}. {action['type']}")
                details = action['details']
                print(f"   Position: ({details.get('x', 0)}, {details.get('y', 0)})")
                print(f"   Size: {details.get('width', 0)} x {details.get('height', 0)}")
                print(f"   Text: {details.get('text', '')[:50]}")
                print(f"   Class: {details.get('className', '')[:50]}")
                print()

            print("=" * 70)
            print("\nPlease send me the content of recorded_actions.json")
            print("so I can generate the automation code for you.\n")
            print("=" * 70)

            await page.wait_for_timeout(30000)

        finally:
            await context.close()
            await browser.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nRecording stopped by user.")
