"""
POLARIS — Time-Series Historical Data Migration Utility to Supabase
Migrates existing SQLite telemetry and alert history to Supabase Cloud PostgreSQL.
Preserves exact timestamps, steps, and numerical precision.
"""
import os
import sys
import sqlite3
from typing import Dict, Any, List

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from database.database import SUPABASE_URL, SUPABASE_KEY, DEFAULT_DB_PATH
from supabase import create_client

def migrate():
    print(f"Connecting to Supabase at: {SUPABASE_URL}")
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    if not os.path.exists(DEFAULT_DB_PATH):
        print(f"No local database found at {DEFAULT_DB_PATH}. Nothing to migrate.")
        return

    conn = sqlite3.connect(DEFAULT_DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 1. Migrate Telemetry
    try:
        cursor.execute("SELECT * FROM telemetry ORDER BY id ASC")
        rows = cursor.fetchall()
        print(f"Found {len(rows)} local telemetry time-series records.")

        batch_size = 50
        batch = []
        migrated = 0
        for r in rows:
            d = dict(r)
            d.pop("id", None)  # Let Supabase assign or generate ID
            batch.append(d)
            if len(batch) >= batch_size:
                supabase.table("telemetry").insert(batch).execute()
                migrated += len(batch)
                print(f"  Migrated {migrated}/{len(rows)} telemetry rows...")
                batch = []
        if batch:
            supabase.table("telemetry").insert(batch).execute()
            migrated += len(batch)
            print(f"  Completed telemetry migration: {migrated} rows.")
    except Exception as e:
        print(f"Telemetry migration notice (tables may need to be created first): {e}")

    # 2. Migrate Alerts
    try:
        cursor.execute("SELECT * FROM alerts ORDER BY id ASC")
        rows = cursor.fetchall()
        print(f"Found {len(rows)} local alert records.")
        batch = []
        for r in rows:
            d = dict(r)
            d.pop("id", None)
            batch.append(d)
        if batch:
            supabase.table("alerts").insert(batch).execute()
            print(f"  Migrated {len(batch)} alerts.")
    except Exception as e:
        print(f"Alerts migration notice: {e}")

    # 3. Migrate AI Decisions
    try:
        cursor.execute("SELECT * FROM ai_decisions ORDER BY id ASC")
        rows = cursor.fetchall()
        print(f"Found {len(rows)} local AI decision records.")
        batch = []
        for r in rows:
            d = dict(r)
            d.pop("id", None)
            batch.append(d)
        if batch:
            supabase.table("ai_decisions").insert(batch).execute()
            print(f"  Migrated {len(batch)} AI decisions.")
    except Exception as e:
        print(f"AI decisions migration notice: {e}")

    conn.close()
    print("Migration script execution finished.")

if __name__ == "__main__":
    migrate()
