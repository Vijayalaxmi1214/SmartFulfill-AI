import csv
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from config.settings import BASE_DIR, DATA_DIR, EXPORT_DIR, RANDOM_SEED, create_directories
from database.db_manager import get_connection


def hash_file(filepath):
    """Compute SHA-256 hash of a file."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def export_all_data():
    create_directories()
    connection = get_connection()

    manifest = {
        "system": "SmartFulfill AI",
        "version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "random_seed": RANDOM_SEED,
        "provenance": "100% synthetically generated via rule-based fulfillment engine. No external confidential/PII data used.",
        "tables": {},
        "files": {},
    }

    print("=" * 65)
    print("       SMARTFULFILL AI — EXPORT SEED DATA & MANIFEST")
    print("=" * 65)

    try:
        cursor = connection.cursor()
        tables = cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
        """).fetchall()

        table_names = [t[0] for t in tables]
        print(f"Exporting {len(table_names)} tables to {EXPORT_DIR}...")

        # 1. Export CSV for every table
        for table in table_names:
            cur = connection.execute(f"SELECT * FROM {table}")
            cols = [desc[0] for desc in cur.description]
            csv_path = EXPORT_DIR / f"{table}.csv"

            row_count = 0
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(cols)
                for row in cur:
                    writer.writerow(tuple(row))
                    row_count += 1

            sha256 = hash_file(csv_path)
            file_size = csv_path.stat().st_size

            manifest["tables"][table] = {
                "records": row_count,
                "columns": cols,
                "csv_file": f"data/exports/{table}.csv",
                "sha256": sha256,
                "bytes": file_size,
            }
            print(f"  -> Exported {table:26} ({row_count:>6} rows) | SHA256: {sha256[:12]}...")

        # 2. Export SQL Dump
        sql_dump_path = EXPORT_DIR / "smartfulfill_seed.sql"
        with open(sql_dump_path, "w", encoding="utf-8") as f:
            for line in connection.iterdump():
                f.write(f"{line}\n")
        manifest["files"]["smartfulfill_seed.sql"] = {
            "path": "data/exports/smartfulfill_seed.sql",
            "bytes": sql_dump_path.stat().st_size,
            "sha256": hash_file(sql_dump_path),
        }
        print(f"\n  -> SQL dump saved to: {sql_dump_path}")

        # 3. Export Source Manifest
        manifest_path = DATA_DIR / "source_manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=4)
        print(f"  -> Source manifest saved to: {manifest_path}")

        print("\nEXPORT COMPLETED SUCCESSFULLY")
        return manifest

    finally:
        connection.close()


if __name__ == "__main__":
    export_all_data()
