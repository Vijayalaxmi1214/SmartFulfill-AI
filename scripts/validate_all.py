import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from config.settings import GROUND_TRUTH_DIR
from database.db_manager import get_connection, validate_database


def run_comprehensive_validation():
    print("=" * 65)
    print("       SMARTFULFILL AI — COMPREHENSIVE SYSTEM VALIDATION")
    print("=" * 65)

    connection = get_connection()
    violations = []
    anomalies_detected = []

    try:
        cursor = connection.cursor()

        # -------------------------------------------------------------
        # 1. DATABASE INTEGRITY & FOREIGN KEY ENFORCEMENT
        # -------------------------------------------------------------
        print("\n[CHECK 1/8] SQLite Integrity & Foreign Keys...")
        db_result = validate_database()
        if db_result["integrity"] != "ok":
            violations.append(f"Integrity check failed: {db_result['integrity']}")
        if db_result["foreign_key_errors"] > 0:
            violations.append(f"Foreign key violations found: {db_result['foreign_key_errors']}")
        print(f"  -> Integrity: {db_result['integrity']} | FK Errors: {db_result['foreign_key_errors']}")

        # -------------------------------------------------------------
        # 2. PRIMARY KEY UNIQUENESS & NOT-NULL ENFORCEMENT
        # -------------------------------------------------------------
        print("\n[CHECK 2/8] Primary Key Uniqueness & Non-Null Checks...")
        pk_checks = [
            ("orders", "order_id"),
            ("order_lines", "order_line_id"),
            ("skus", "sku_id"),
            ("fulfillment_nodes", "node_id"),
            ("inventory", "inventory_id"),
            ("warehouse_capacity", "capacity_id"),
            ("carriers", "carrier_id"),
            ("service_levels", "service_level_id"),
            ("shipments", "shipment_id"),
            ("tracking_events", "tracking_event_id"),
            ("delivery_promises", "promise_id"),
        ]
        for table, pk in pk_checks:
            dup_count = cursor.execute(f"""
                SELECT COUNT(*) FROM (
                    SELECT {pk}, COUNT(*) c FROM {table} GROUP BY {pk} HAVING c > 1
                )
            """).fetchone()[0]
            null_count = cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE {pk} IS NULL").fetchone()[0]
            if dup_count > 0 or null_count > 0:
                violations.append(f"PK issue in {table}({pk}): {dup_count} duplicates, {null_count} nulls")
            else:
                total = cursor.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                print(f"  -> [OK] {table}.{pk} is unique ({total} records)")

        # -------------------------------------------------------------
        # 3. ALLOWED ENUMS AND VALUE CONSTRAINTS
        # -------------------------------------------------------------
        print("\n[CHECK 3/8] Allowed Enums and Value Domain Checks...")
        enum_checks = [
            ("orders", "order_status", "('CREATED', 'ALLOCATED', 'PARTIALLY_ALLOCATED', 'UNFULFILLED', 'SHIPPED', 'PARTIALLY_DELIVERED', 'DELIVERED', 'CANCELLED')"),
            ("shipments", "shipment_status", "('CREATED', 'ALLOCATED', 'DISPATCHED', 'IN_TRANSIT', 'OUT_FOR_DELIVERY', 'DELIVERED', 'FAILED', 'CANCELLED')"),
            ("fulfillment_nodes", "node_type", "('WAREHOUSE', 'STORE')"),
            ("delivery_promises", "promise_status", "('ACTIVE', 'SUPERSEDED', 'FULFILLED')"),
            ("tracking_events", "event_code", "('LABEL_CREATED', 'PICKED_UP', 'DISPATCHED', 'IN_TRANSIT', 'ARRIVED_AT_HUB', 'OUT_FOR_DELIVERY', 'DELIVERED', 'DELIVERY_FAILED')"),
        ]
        for table, col, allowed in enum_checks:
            invalid = cursor.execute(f"""
                SELECT COUNT(*) FROM {table} WHERE {col} NOT IN {allowed}
            """).fetchone()[0]
            if invalid > 0:
                violations.append(f"Invalid enum values in {table}.{col}: {invalid} rows")
            else:
                print(f"  -> [OK] {table}.{col} enum domain verified")

        # -------------------------------------------------------------
        # 4. CHRONOLOGY & DATE ORDERING (Detecting Promise & Delivery Anomaly)
        # -------------------------------------------------------------
        print("\n[CHECK 4/8] Date & Timestamp Chronology Checks...")
        # 4a. Promise date >= Order date
        promise_anomalies = cursor.execute("""
            SELECT dp.promise_id, o.order_id, dp.promised_delivery_date, o.order_created_at
            FROM delivery_promises dp
            JOIN orders o ON o.order_id = dp.order_id
            WHERE dp.promise_status = 'ACTIVE'
              AND dp.promised_delivery_date < SUBSTR(o.order_created_at, 1, 10)
        """).fetchall()
        for p in promise_anomalies:
            anomalies_detected.append({
                "type": "PROMISE_BEFORE_ORDER_TIME",
                "entity": p["promise_id"],
                "details": f"Promised {p['promised_delivery_date']} is before order date {p['order_created_at']}"
            })
        print(f"  -> Promise vs Order Date: {len(promise_anomalies)} anomalies found")

        # 4b. Dispatched <= Delivered
        dispatch_anomalies = cursor.execute("""
            SELECT shipment_id, dispatched_at, delivered_at
            FROM shipments
            WHERE dispatched_at IS NOT NULL
              AND delivered_at IS NOT NULL
              AND delivered_at < dispatched_at
        """).fetchall()
        for d in dispatch_anomalies:
            anomalies_detected.append({
                "type": "SHIPMENT_DELIVERED_BEFORE_DISPATCH",
                "entity": d["shipment_id"],
                "details": f"Delivered {d['delivered_at']} before dispatch {d['dispatched_at']}"
            })
        print(f"  -> Dispatch vs Delivery Chronology: {len(dispatch_anomalies)} anomalies found")

        # -------------------------------------------------------------
        # 5. ARITHMETIC RECONCILIATION & STOCK BOUNDARIES
        # -------------------------------------------------------------
        print("\n[CHECK 5/8] Inventory & Capacity Arithmetic Reconciliation...")
        # Stock violations (allocated / reserved > on_hand)
        stock_violations = cursor.execute("""
            SELECT sl.shipment_line_id, sl.order_line_id, sl.allocated_quantity,
                   i.on_hand_quantity, i.inventory_id
            FROM shipment_lines sl
            JOIN order_lines ol ON ol.order_line_id = sl.order_line_id
            JOIN shipments s ON s.shipment_id = sl.shipment_id
            JOIN inventory i ON i.node_id = s.node_id AND i.sku_id = ol.sku_id
            WHERE sl.allocated_quantity > i.on_hand_quantity
        """).fetchall()
        for sv in stock_violations:
            anomalies_detected.append({
                "type": "ALLOCATION_EXCEEDS_STOCK",
                "entity": sv["shipment_line_id"],
                "details": f"Allocated qty {sv['allocated_quantity']} exceeds on hand {sv['on_hand_quantity']}"
            })
        print(f"  -> Stock Boundary Checks: {len(stock_violations)} anomalies found")

        # Capacity violations
        capacity_violations = cursor.execute("""
            SELECT capacity_id, max_units, reserved_units
            FROM warehouse_capacity
            WHERE reserved_units > max_units
        """).fetchall()
        if capacity_violations:
            violations.append(f"{len(capacity_violations)} warehouse capacity overflow records found")
        else:
            print("  -> [OK] All warehouse capacity reservations within max limits")

        # -------------------------------------------------------------
        # 6. CARRIER ROUTING & ZONE COMPATIBILITY
        # -------------------------------------------------------------
        print("\n[CHECK 6/8] Carrier Service & Zone Compatibility...")
        routing_anomalies = cursor.execute("""
            SELECT s.shipment_id, s.carrier_id, s.service_level_id, o.destination_zone_id
            FROM shipments s
            JOIN orders o ON o.order_id = s.order_id
            WHERE NOT EXISTS (
                SELECT 1 FROM carrier_services cs
                WHERE cs.carrier_id = s.carrier_id
                  AND cs.service_level_id = s.service_level_id
                  AND cs.zone_id = o.destination_zone_id
            )
        """).fetchall()
        for r in routing_anomalies:
            anomalies_detected.append({
                "type": "CARRIER_SERVICE_UNSUPPORTED_FOR_ZONE",
                "entity": r["shipment_id"],
                "details": f"Carrier {r['carrier_id']} / {r['service_level_id']} does not serve zone {r['destination_zone_id']}"
            })
        print(f"  -> Carrier Service Routing: {len(routing_anomalies)} unsupported routes found")

        # -------------------------------------------------------------
        # 7. ORDER LIFECYCLE & SPLIT SHIPMENT ROLLUP
        # -------------------------------------------------------------
        print("\n[CHECK 7/8] Split Shipment Status Rollup Consistency...")
        split_mismatches = cursor.execute("""
            WITH order_summary AS (
                SELECT
                    o.order_id,
                    o.order_status,
                    COUNT(s.shipment_id) as total_shipments,
                    SUM(CASE WHEN s.shipment_status = 'DELIVERED' THEN 1 ELSE 0 END) as delivered_cnt,
                    SUM(CASE WHEN s.shipment_status = 'FAILED' THEN 1 ELSE 0 END) as failed_cnt
                FROM orders o
                JOIN shipments s ON s.order_id = o.order_id
                GROUP BY o.order_id
            )
            SELECT * FROM order_summary
            WHERE total_shipments > 1
              AND (
                  (delivered_cnt < total_shipments AND delivered_cnt > 0 AND order_status = 'DELIVERED')
                  OR (delivered_cnt = total_shipments AND order_status != 'DELIVERED')
              )
        """).fetchall()
        for sm in split_mismatches:
            anomalies_detected.append({
                "type": "SPLIT_SHIPMENT_STATUS_NOT_ROLLED_UP",
                "entity": sm["order_id"],
                "details": f"Order marked '{sm['order_status']}' but has {sm['delivered_cnt']}/{sm['total_shipments']} shipments delivered"
            })
        print(f"  -> Split Shipment Rollup Checks: {len(split_mismatches)} mismatches found")

        # -------------------------------------------------------------
        # 8. GROUND TRUTH RECONCILIATION
        # -------------------------------------------------------------
        print("\n[CHECK 8/8] Ground Truth Catalog Reconciliation...")
        gt_file = GROUND_TRUTH_DIR / "ground_truth.json"
        if gt_file.exists():
            with open(gt_file, "r", encoding="utf-8") as f:
                ground_truth = json.load(f)
            print(f"  -> Ground truth catalog contains {len(ground_truth)} known labelled anomalies.")
            print(f"  -> Total anomalies detected in DB scan: {len(anomalies_detected)}")

            gt_types = {item["edge_case_type"] for item in ground_truth}
            detected_types = {item["type"] for item in anomalies_detected}

            matched = gt_types.intersection(detected_types)
            print(f"  -> Successfully detected {len(matched)} of {len(gt_types)} ground truth anomaly types: {matched}")
        else:
            print("  -> No ground_truth.json found. System running in pure clean baseline mode.")

        # -------------------------------------------------------------
        # SUMMARY
        # -------------------------------------------------------------
        print("\n" + "=" * 65)
        print("VALIDATION SUMMARY")
        print("=" * 65)
        if violations:
            print(f"FAILED with {len(violations)} structural/schema violations:")
            for v in violations:
                print("  [ERROR]", v)
            return False
        else:
            print("STRUCTURAL & RELATIONAL INTEGRITY: 100% PASSED")
            print(f"ANOMALIES/EDGE CASES DETECTED   : {len(anomalies_detected)}")
            for a in anomalies_detected:
                print(f"  - [{a['type']}] on {a['entity']}: {a['details']}")
            return True

    finally:
        connection.close()


if __name__ == "__main__":
    success = run_comprehensive_validation()
    sys.exit(0 if success else 1)
