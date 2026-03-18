#!/usr/bin/env python
"""
Custom server startup script for Windows Playwright compatibility

Sets WindowsProactorEventLoopPolicy before uvicorn starts.
This avoids Windows asyncio subprocess issues with Playwright.

IMPORTANT: Does NOT support --reload mode because reload will reset the event loop policy.
"""
import sys
import asyncio

# Set Windows ProactorEventLoop BEFORE importing uvicorn
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    print("✓ Windows ProactorEventLoop policy set (required for Playwright subprocess support)")

import uvicorn

if __name__ == "__main__":
    # Parse command line args
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000, help="Port number")
    args = parser.parse_args()

    # Start server (NO RELOAD - reload will break event loop policy)
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=args.port,
        log_level="info"
    )
