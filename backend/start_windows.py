#!/usr/bin/env python
"""
Custom server startup script for Windows Playwright compatibility.

Sets WindowsProactorEventLoopPolicy before uvicorn starts. This avoids Windows
asyncio subprocess issues with Playwright. Reload is intentionally unsupported
because it resets the event loop policy.
"""

import asyncio
import sys


if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    print("Windows ProactorEventLoop policy enabled")

import uvicorn


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000, help="Port number")
    args = parser.parse_args()

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=args.port,
        log_level="info",
        proxy_headers=False,
    )
