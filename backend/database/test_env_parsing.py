"""
Direct .env file parsing test

This bypasses pydantic-settings to see what's actually in the file.
"""

import os
from pathlib import Path

# Find .env file
env_file = Path(__file__).parent.parent / '.env'
print(f"Reading .env from: {env_file}")
print(f"File exists: {env_file.exists()}")
print()

if not env_file.exists():
    print("ERROR: .env file not found!")
    exit(1)

# Read and parse manually
print("=" * 60)
print("Manual .env parsing")
print("=" * 60)

with open(env_file, 'r', encoding='utf-8') as f:
    for line_num, line in enumerate(f, 1):
        if 'SQLSERVER_PASSWORD' in line:
            print(f"Line {line_num}: {repr(line)}")

            # Try to extract value
            if '=' in line and not line.strip().startswith('#'):
                key, value = line.split('=', 1)
                value = value.strip()

                # Remove quotes if present
                if (value.startswith('"') and value.endswith('"')) or \
                   (value.startswith("'") and value.endswith("'")):
                    value = value[1:-1]

                print(f"  Key: {repr(key.strip())}")
                print(f"  Raw value: {repr(value)}")
                print(f"  Value length: {len(value)} chars")
                print(f"  First char: {repr(value[0]) if value else 'EMPTY'}")

print()
print("=" * 60)
print("Using python-dotenv (alternative parser)")
print("=" * 60)

try:
    from dotenv import dotenv_values

    config = dotenv_values(env_file)
    password = config.get('SQLSERVER_PASSWORD', '')

    print(f"Password: {'*' * len(password)} ({len(password)} chars)")
    if password:
        print(f"First char: {repr(password[0])}")
        print(f"Last char: {repr(password[-1])}")
    else:
        print("ERROR: Password is empty!")

except ImportError:
    print("python-dotenv not installed, skipping")
    print("Install with: pip install python-dotenv")

print()
print("=" * 60)
print("Using pydantic-settings (current method)")
print("=" * 60)

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import settings

print(f"Password: {'*' * len(settings.sqlserver_password)} ({len(settings.sqlserver_password)} chars)")

if not settings.sqlserver_password:
    print()
    print("ERROR: Password is empty in pydantic-settings!")
    print()
    print("Possible causes:")
    print("1. The # character is being treated as a comment start")
    print("2. Quotes are not being handled correctly")
    print("3. The value needs to be escaped differently")
    print()
    print("Try these fixes in .env:")
    print("  Option 1: Remove quotes entirely and escape the #")
    print("    SQLSERVER_PASSWORD=\\#Ph981,6J2bOkWYT7p?5slH$I~g_0itR")
    print()
    print("  Option 2: Use export syntax")
    print("    export SQLSERVER_PASSWORD='#Ph981,6J2bOkWYT7p?5slH$I~g_0itR'")
    print()
    print("  Option 3: Set as actual environment variable")
    print("    set SQLSERVER_PASSWORD=#Ph981,6J2bOkWYT7p?5slH$I~g_0itR")
else:
    print(f"First char: {repr(settings.sqlserver_password[0])}")
    print(f"Last char: {repr(settings.sqlserver_password[-1])}")
    print()
    print("SUCCESS: Password loaded correctly!")
