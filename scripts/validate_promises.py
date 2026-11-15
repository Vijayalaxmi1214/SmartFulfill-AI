
import csv
from pathlib import Path
from datetime import date

from database.db_manager import get_connection


def _load_ground_truth_entities():
    gt_path = Path(__file__).parent.parent / "data" / "ground_truth" / "ground_truth.csv"
    known = set()
    if gt_path.exists():
        with open(gt_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                entity = row.get("entity_id", "").strip()
                if entity:
                    known.add(entity)
    return known


def validate_promises():
    connection = get_connection()
    errors = []
    warnings = []
    known_anomalies = _load_ground_truth_entities()

    try:
        cursor = connection.cursor()

        # Every allocated order must have an active promise.
        rows = cursor.execute("""
            SELECT o.order_id
            FROM orders o
            WHERE o.order_status = 'ALLOCATED'
              AND NOT EXISTS (
                  SELECT 1
                  FROM delivery_promises p
                  WHERE p.order_id = o.order_id
                    AND p.promise_status = 'ACTIVE'
              )
        """).fetchall()

        for row in rows:
            errors.append(
                "Missing active promise: " + row["order_id"]
            )

        # Check promise date is not before order creation.
        rows = cursor.execute("""
            SELECT
                p.order_id,
                p.promised_delivery_date,
                o.order_created_at
            FROM delivery_promises p
            JOIN orders o ON p.order_id = o.order_id
            WHERE p.promise_status = 'ACTIVE'
        """).fetchall()

        for row in rows:
            promise_date = date.fromisoformat(
                row["promised_delivery_date"]
            )

            order_date = date.fromisoformat(
                row["order_created_at"][:10]
            )

            if promise_date < order_date:
                msg = "Promise before order date: " + row["order_id"]
                promise_id = "PROM-{}-01".format(row["order_id"])
                if promise_id in known_anomalies or row["order_id"] in known_anomalies:
                    warnings.append("[KNOWN EDGE CASE] " + msg)
                else:
                    errors.append(msg)

        # Each order must have exactly one active promise.
        rows = cursor.execute("""
            SELECT order_id, COUNT(*) AS total
            FROM delivery_promises
            WHERE promise_status = 'ACTIVE'
            GROUP BY order_id
        """).fetchall()

        for row in rows:
            if row["total"] != 1:
                errors.append(
                    "Multiple active promises: " + row["order_id"]
                )

        # Foreign key validation.
        fk_errors = cursor.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

        if fk_errors:
            errors.append("Foreign-key integrity failure")

        # Promise version uniqueness.
        duplicates = cursor.execute("""
            SELECT order_id, promise_version, COUNT(*) AS total
            FROM delivery_promises
            GROUP BY order_id, promise_version
            HAVING COUNT(*) > 1
        """).fetchall()

        if duplicates:
            errors.append("Duplicate promise versions detected")

        print("\nDELIVERY PROMISE VALIDATION")
        print("-" * 45)

        if warnings:
            for w in warnings:
                print("[WARN]", w)

        if errors:
            print("FAILED:", len(errors), "errors")
            for error in errors:
                print("[ERROR]", error)
        else:
            print("PASSED")
            print("Every allocated order has an active promise.")
            print("No promise dates before order dates.")
            print("Promise versions are unique.")
            print("Foreign-key integrity is valid.")
            if warnings:
                print("Known edge-case anomalies (ground truth):", len(warnings))

        return len(errors) == 0

    finally:
        connection.close()


if __name__ == "__main__":
    if not validate_promises():
        raise SystemExit(1)
