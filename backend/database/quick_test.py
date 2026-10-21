"""
Quick connection string test

This script tests the SQL Server connection with the updated password handling.
"""

import sys
import os

# Add backend path to sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from config.settings import settings

print("=" * 60)
print("SQL Server Connection String Test")
print("=" * 60)
print()

print("Settings loaded from .env:")
print(f"  Host: {settings.sqlserver_host}")
print(f"  Port: {settings.sqlserver_port}")
print(f"  Database: {settings.sqlserver_database}")
print(f"  User: {settings.sqlserver_user}")
print(f"  Password: {'*' * len(settings.sqlserver_password)} ({len(settings.sqlserver_password)} chars)")
print(f"  Driver: {settings.sqlserver_driver}")
print()

# Show connection string (with masked password)
conn_str = settings.sqlserver_connection_string
# Mask password in display
import re
masked_conn_str = re.sub(r'PWD=\{[^}]+\}', 'PWD={********}', conn_str)
print("Connection string (password masked):")
print(f"  {masked_conn_str}")
print()

# Test actual password characters
print("Password analysis:")
special_chars = set()
for char in settings.sqlserver_password:
    if not char.isalnum():
        special_chars.add(char)

if special_chars:
    print(f"  Contains special characters: {', '.join(sorted(special_chars))}")
    print(f"  These will be properly escaped in the connection string")
else:
    print(f"  No special characters detected")
print()

# Try to import and test pyodbc
print("Testing pyodbc import...")
try:
    import pyodbc
    print("  [OK] pyodbc is installed")

    # List available drivers
    drivers = pyodbc.drivers()
    print(f"\n  Available ODBC drivers ({len(drivers)}):")
    for driver in drivers:
        marker = " <-- CONFIGURED" if driver == settings.sqlserver_driver else ""
        print(f"    - {driver}{marker}")

    if settings.sqlserver_driver not in drivers:
        print(f"\n  [WARNING] Configured driver '{settings.sqlserver_driver}' not found!")
        print(f"  Available drivers: {', '.join(drivers)}")

except ImportError:
    print("  [ERROR] pyodbc is not installed")
    print("  Please run: pip install pyodbc aioodbc")
    sys.exit(1)

print()
print("=" * 60)
print("Quick connection test...")
print("=" * 60)

try:
    import pyodbc

    # Test connection
    print("Attempting to connect...")
    conn = pyodbc.connect(conn_str)
    print("[SUCCESS] Connection established!")

    # Test a simple query
    cursor = conn.cursor()
    cursor.execute("SELECT @@VERSION")
    version = cursor.fetchone()
    print(f"\nSQL Server version:")
    print(f"  {version[0][:100]}...")

    # Check if database exists
    cursor.execute("SELECT DB_NAME()")
    db_name = cursor.fetchone()[0]
    print(f"\nCurrent database: {db_name}")

    # Check if table exists
    cursor.execute("""
        SELECT COUNT(*)
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_NAME = 'analysis_history'
    """)
    table_exists = cursor.fetchone()[0] > 0

    if table_exists:
        print(f"[OK] Table 'analysis_history' exists")

        # Count records
        cursor.execute("SELECT COUNT(*) FROM analysis_history")
        count = cursor.fetchone()[0]
        print(f"  Total records: {count}")
    else:
        print(f"[INFO] Table 'analysis_history' does not exist yet")
        print(f"  Please run the initialization script:")
        print(f"    init_database.bat  (Windows)")
        print(f"    ./init_database.sh (Linux/macOS)")

    cursor.close()
    conn.close()

    print()
    print("=" * 60)
    print("[SUCCESS] All tests passed!")
    print("=" * 60)
    print()
    print("Next steps:")
    if not table_exists:
        print("1. Run database initialization script")
        print("2. Run full test: python test_database_connection.py")
    else:
        print("1. Run full test: python test_database_connection.py")
        print("2. Start backend: cd .. && python -m uvicorn app.main:app --reload")

except Exception as e:
    print(f"\n[ERROR] Connection failed: {str(e)}")
    print()
    print("Troubleshooting:")
    print("1. Verify SQL Server is running and accessible")
    print("2. Check firewall settings for port 1433")
    print("3. Verify credentials in .env file")
    print("4. Ensure ODBC driver is installed")
    print()

    import traceback
    print("Detailed error:")
    traceback.print_exc()
    sys.exit(1)
