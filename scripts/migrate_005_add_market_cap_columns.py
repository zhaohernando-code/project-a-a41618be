#!/usr/bin/env python3
"""Migration 005: Add market cap columns to market_bars table.

Adds total_mv, circ_mv, pe_ttm, pb columns for size factor computation.
Idempotent: uses IF NOT EXISTS via catching duplicate column errors.
"""

import sqlite3
import sys

DB_PATH = "/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/ashare_dashboard.db"

COLUMNS = [
    ("total_mv", "REAL"),
    ("circ_mv", "REAL"),
    ("pe_ttm", "REAL"),
    ("pb", "REAL"),
]


def run_migration(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Verify table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='market_bars'")
    if not cursor.fetchone():
        print("ERROR: market_bars table does not exist.")
        sys.exit(1)

    # Get existing columns
    cursor.execute("PRAGMA table_info(market_bars)")
    existing = {row[1] for row in cursor.fetchall()}

    for col_name, col_type in COLUMNS:
        if col_name in existing:
            print(f"Column '{col_name}' already exists, skipping.")
            continue
        try:
            cursor.execute(f"ALTER TABLE market_bars ADD COLUMN {col_name} {col_type}")
            print(f"Added column '{col_name}' ({col_type}).")
        except sqlite3.OperationalError as exc:
            if "duplicate column" in str(exc).lower():
                print(f"Column '{col_name}' already exists (caught error), skipping.")
            else:
                print(f"ERROR adding column '{col_name}': {exc}")
                conn.rollback()
                sys.exit(1)

    conn.commit()
    conn.close()
    print("Migration 005 completed successfully.")


if __name__ == "__main__":
    run_migration(DB_PATH)
