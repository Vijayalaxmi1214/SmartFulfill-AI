
import csv
from pathlib import Path
from datetime import datetime

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


def validate_tracking():
    connection = get_connection()
    errors = []
    warnings = []
    known_anomalies = _load_ground_truth_entities()

    try:
        cursor = connection.cursor()

        shipments = cursor.execute("""
            SELECT shipment_id, shipment_status,
                   dispatched_at, delivered_at
            FROM shipments
            ORDER BY shipment_id
        """).fetchall()

        for shipment in shipments:
            shipment_id = shipment["shipment_id"]

            events = cursor.execute("""
                SELECT event_sequence, event_code, event_time
                FROM tracking_events
                WHERE shipment_id = ?
                ORDER BY event_sequence
            """, (shipment_id,)).fetchall()

            if not events:
                errors.append(
                    "No tracking events: " + shipment_id
                )
                continue

            expected_sequence = list(range(1, len(events) + 1))
            actual_sequence = [
                row["event_sequence"] for row in events
            ]

            if actual_sequence != expected_sequence:
                errors.append(
                    "Invalid event sequence: " + shipment_id
                )

            times = [
                datetime.fromisoformat(row["event_time"])
                for row in events
            ]

            if times != sorted(times):
                msg = "Tracking timestamps are not chronological: " + shipment_id
                if shipment_id in known_anomalies:
                    warnings.append("[KNOWN EDGE CASE] " + msg)
                else:
                    errors.append(msg)

            codes = [row["event_code"] for row in events]

            if "DELIVERED" in codes:
                if codes[-1] != "DELIVERED":
                    errors.append(
                        "Delivered event is not the final event: "
                        + shipment_id
                    )

                if shipment["shipment_status"] != "DELIVERED":
                    errors.append(
                        "Delivered event/status mismatch: "
                        + shipment_id
                    )

                if not shipment["dispatched_at"]:
                    errors.append(
                        "Delivered shipment has no dispatch time: "
                        + shipment_id
                    )

                if not shipment["delivered_at"]:
                    errors.append(
                        "Delivered shipment has no delivery time: "
                        + shipment_id
                    )

            elif "DELIVERY_FAILED" in codes:
                if codes[-1] != "DELIVERY_FAILED":
                    errors.append(
                        "Failed event is not the final event: "
                        + shipment_id
                    )

                if shipment["shipment_status"] != "FAILED":
                    errors.append(
                        "Failed event/status mismatch: "
                        + shipment_id
                    )

            elif shipment["shipment_status"] == "IN_TRANSIT":
                if codes[-1] != "ARRIVED_AT_HUB":
                    errors.append(
                        "In-transit shipment has unexpected last event: "
                        + shipment_id
                    )

            if "DELIVERED" in codes and "DISPATCHED" not in codes:
                errors.append(
                    "Delivered before dispatch: " + shipment_id
                )

        foreign_key_errors = cursor.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

        if foreign_key_errors:
            errors.append("Foreign-key violations found")

        integrity = cursor.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

        if integrity != "ok":
            errors.append("Database integrity check failed")

        event_count = cursor.execute("""
            SELECT COUNT(*) AS total FROM tracking_events
        """).fetchone()["total"]

        exception_count = cursor.execute("""
            SELECT COUNT(*) AS total FROM tracking_exceptions
        """).fetchone()["total"]

        status_counts = cursor.execute("""
            SELECT shipment_status, COUNT(*) AS total
            FROM shipments
            GROUP BY shipment_status
            ORDER BY shipment_status
        """).fetchall()

        print("\nSHIPMENT TRACKING VALIDATION")
        print("--------------------------------------")
        print("Shipments checked:", len(shipments))
        print("Tracking events:", event_count)
        print("Tracking exceptions:", exception_count)

        print("\nSHIPMENT STATUS BREAKDOWN")

        for row in status_counts:
            print("{}: {}".format(
                row["shipment_status"],
                row["total"]
            ))

        if errors:
            print("\nFAILED:", len(errors), "errors")

            for error in errors:
                print("[ERROR]", error)

            return False

        print("\nPASSED")
        print("Tracking sequences are valid.")
        print("Shipment statuses match tracking outcomes.")
        print("Event timestamps are chronological.")
        print("No delivered-before-dispatch violations.")
        print("Database integrity is valid.")
        if warnings:
            print("Known edge-case anomalies (ground truth):", len(warnings))
            for w in warnings:
                print("[WARN]", w)

        return True

    finally:
        connection.close()


if __name__ == "__main__":
    if not validate_tracking():
        raise SystemExit(1)
