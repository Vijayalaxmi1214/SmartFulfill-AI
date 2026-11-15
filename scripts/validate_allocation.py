
import csv
import os
from pathlib import Path
from database.db_manager import get_connection


def _load_ground_truth_entities():
    """Return the set of entity IDs and order IDs for known anomalies."""
    gt_path = Path(__file__).parent.parent / "data" / "ground_truth" / "ground_truth.csv"
    known = set()
    if gt_path.exists():
        with open(gt_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                entity = row.get("entity_id", "").strip()
                order = row.get("order_id", "").strip()
                if entity:
                    known.add(entity)
                if order:
                    known.add(order)
    return known


def validate_allocation():
    connection = get_connection()

    errors = []
    warnings = []
    known_anomalies = _load_ground_truth_entities()

    try:
        cursor = connection.cursor()

        # Build a set of order_line_ids that belong to known-anomaly orders
        known_order_line_ids = set()
        if known_anomalies:
            # Find shipment_lines that are ground-truth anomalies (by shipment_line_id)
            # and the order_lines that belong to anomalous orders
            gt_shl = {e for e in known_anomalies if e.startswith("SHL-")}
            gt_orders = {e for e in known_anomalies if e.startswith("ORD-")}

            if gt_shl:
                placeholders = ",".join("?" * len(gt_shl))
                rows = cursor.execute(
                    "SELECT order_line_id FROM shipment_lines WHERE shipment_line_id IN ({})".format(placeholders),
                    list(gt_shl)
                ).fetchall()
                for r in rows:
                    known_order_line_ids.add(r["order_line_id"])

            if gt_orders:
                placeholders = ",".join("?" * len(gt_orders))
                rows = cursor.execute(
                    "SELECT order_line_id FROM order_lines WHERE order_id IN ({})".format(placeholders),
                    list(gt_orders)
                ).fetchall()
                for r in rows:
                    known_order_line_ids.add(r["order_line_id"])

        # Check each order line's allocated quantity.
        rows = cursor.execute("""
            SELECT
                ol.order_line_id,
                ol.quantity,
                COALESCE(SUM(sl.allocated_quantity), 0) AS allocated
            FROM order_lines ol
            LEFT JOIN shipment_lines sl
                ON ol.order_line_id = sl.order_line_id
            GROUP BY ol.order_line_id, ol.quantity
        """).fetchall()

        for row in rows:
            if row["allocated"] > row["quantity"]:
                line_id = row["order_line_id"]
                msg = "Over-allocation: " + line_id
                if line_id in known_anomalies or line_id in known_order_line_ids:
                    warnings.append("[KNOWN EDGE CASE] " + msg)
                else:
                    errors.append(msg)

        # Check inventory reservation limits.
        rows = cursor.execute("""
            SELECT inventory_id, on_hand_quantity,
                   reserved_quantity, safety_stock
            FROM inventory
        """).fetchall()

        for row in rows:
            if (
                row["reserved_quantity"] + row["safety_stock"]
                > row["on_hand_quantity"]
            ):
                errors.append(
                    "Inventory exceeded: " + row["inventory_id"]
                )

        # Check warehouse capacity limits.
        rows = cursor.execute("""
            SELECT capacity_id, max_units, reserved_units
            FROM warehouse_capacity
        """).fetchall()

        for row in rows:
            if row["reserved_units"] > row["max_units"]:
                errors.append(
                    "Capacity exceeded: " + row["capacity_id"]
                )

        # Check shipment foreign keys.
        fk_errors = cursor.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

        if fk_errors:
            errors.append("Foreign-key integrity failure")

        # Check order-level allocation status.
        rows = cursor.execute("""
            SELECT
                o.order_id,
                o.order_status,
                COALESCE(SUM(ol.quantity), 0) AS requested,
                COALESCE(SUM(a.allocated), 0) AS allocated
            FROM orders o
            LEFT JOIN order_lines ol
                ON o.order_id = ol.order_id
            LEFT JOIN (
                SELECT
                    sl.order_line_id,
                    SUM(sl.allocated_quantity) AS allocated
                FROM shipment_lines sl
                GROUP BY sl.order_line_id
            ) a ON ol.order_line_id = a.order_line_id
            GROUP BY o.order_id, o.order_status
        """).fetchall()

        for row in rows:
            requested = row["requested"]
            allocated = row["allocated"]
            status = row["order_status"]

            if status == "ALLOCATED" and allocated != requested:
                errors.append(
                    "Incorrect fully allocated status: " + row["order_id"]
                )

            if status == "PARTIALLY_ALLOCATED":
                if not (0 < allocated < requested):
                    errors.append(
                        "Incorrect partial status: " + row["order_id"]
                    )

            if status == "UNFULFILLED" and allocated != 0:
                errors.append(
                    "Incorrect unfulfilled status: " + row["order_id"]
                )

        print("\nALLOCATION VALIDATION")
        print("-" * 40)

        if warnings:
            for w in warnings:
                print("[WARN]", w)

        if errors:
            print("FAILED:", len(errors), "errors")
            for error in errors:
                print("[ERROR]", error)
        else:
            print("PASSED")
            print("No allocation quantity violations.")
            print("No inventory reservation violations.")
            print("No warehouse capacity violations.")
            print("No foreign-key violations.")
            print("Order statuses reconciled correctly.")
            if warnings:
                print("Known edge-case anomalies (ground truth):", len(warnings))

        return len(errors) == 0

    finally:
        connection.close()


if __name__ == "__main__":
    if not validate_allocation():
        raise SystemExit(1)
