import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

from config.settings import BASE_DIR, DATA_DIR, RANDOM_SEED


def hash_sqlite_tables(db_path):
    """Compute row count and deterministic content hash for each table in SQLite DB."""
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    tables = cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
        ORDER BY name
    """).fetchall()

    table_hashes = {}
    for (t,) in tables:
        cur = conn.execute(f"SELECT * FROM {t} ORDER BY 1")
        hasher = hashlib.sha256()
        count = 0
        for row in cur:
            hasher.update(str(tuple(row)).encode("utf-8"))
            count += 1
        table_hashes[t] = {
            "rows": count,
            "hash": hasher.hexdigest(),
        }
    conn.close()
    return table_hashes


def run_pipeline(orders_count=100):
    python_exe = sys.executable
    cmd = [python_exe, "-m", "scripts.generate_data", "--orders", str(orders_count)]
    res = subprocess.run(cmd, cwd=str(BASE_DIR), capture_output=True, text=True)
    if res.returncode != 0:
        print("Pipeline execution failed:")
        print(res.stderr)
        raise RuntimeError("Generation pipeline failed")

    # Run allocation, promises, tracking
    for mod in ["scripts.run_allocation", "scripts.run_promises", "scripts.run_tracking"]:
        r = subprocess.run([python_exe, "-m", mod], cwd=str(BASE_DIR), capture_output=True, text=True)
        if r.returncode != 0:
            print(f"{mod} failed:")
            print(r.stderr)
            raise RuntimeError(f"{mod} failed")


def verify_reproducibility():
    print("=" * 65)
    print("       SMARTFULFILL AI — REPRODUCIBILITY VERIFICATION")
    print("=" * 65)
    print(f"Fixed Random Seed : {RANDOM_SEED}")
    print("Target             : Regenerate twice from scratch and compare hashes")

    db_file = DATA_DIR / "smartfulfill.db"

    # RUN 1
    print("\n[RUN 1] Generating fresh dataset...")
    run_pipeline(orders_count=100)
    hashes_run1 = hash_sqlite_tables(db_file)
    print("  -> Run 1 completed successfully.")

    # RUN 2
    print("\n[RUN 2] Regenerating dataset with identical seed...")
    run_pipeline(orders_count=100)
    hashes_run2 = hash_sqlite_tables(db_file)
    print("  -> Run 2 completed successfully.")

    # COMPARISON
    print("\n" + "=" * 65)
    print(f"{'TABLE NAME':26} | {'RUN 1 ROWS':>10} | {'RUN 2 ROWS':>10} | {'MATCH':>7}")
    print("-" * 65)

    all_matched = True
    for table in sorted(hashes_run1.keys()):
        h1 = hashes_run1[table]
        h2 = hashes_run2.get(table, {})
        rows_match = h1["rows"] == h2.get("rows")
        hash_match = h1["hash"] == h2.get("hash")
        matched = rows_match and hash_match

        status = "[PASS]" if matched else "[FAIL]"
        if not matched:
            all_matched = False
        print(f"{table:26} | {h1['rows']:>10} | {h2.get('rows', 0):>10} | {status:>7}")

    print("=" * 65)
    if all_matched:
        print("REPRODUCIBILITY TEST PASSED: 100% IDENTICAL CHECKSUMS ACROSS RUNS")
        return True
    else:
        print("REPRODUCIBILITY TEST FAILED: Checksums differed between runs.")
        return False


if __name__ == "__main__":
    success = verify_reproducibility()
    sys.exit(0 if success else 1)
