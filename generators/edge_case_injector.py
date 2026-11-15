import csv
import json
from datetime import datetime, timedelta
from pathlib import Path

from config.settings import GROUND_TRUTH_DIR, create_directories
from database.db_manager import get_connection


INJECTION_TIMESTAMP = "2026-11-20T12:00:00"


def inject_edge_cases():
    """Inject the 5 required labeled edge cases/negative scenarios into the dataset

    and record their full ground truth labels in data/ground_truth/.
    """
    create_directories()
    connection = get_connection()

    ground_truth_records = []

    try:
        cursor = connection.cursor()

        # ---------------------------------------------------------------------
        # 1. Edge Case: Promise before order time
        # ---------------------------------------------------------------------
        order_candidate = cursor.execute("""
            SELECT o.order_id, o.order_created_at, dp.promise_id, dp.promised_delivery_date
            FROM orders o
            JOIN delivery_promises dp ON dp.order_id = o.order_id
            WHERE dp.promise_status = 'ACTIVE'
            ORDER BY o.order_id DESC
            LIMIT 1
        """).fetchone()

        if order_candidate:
            order_id = order_candidate["order_id"]
            promise_id = order_candidate["promise_id"]
            created_at = order_candidate["order_created_at"]
            original_promise = order_candidate["promised_delivery_date"]

            order_date = datetime.fromisoformat(created_at).date()
            invalid_promise_date = (order_date - timedelta(days=2)).isoformat()

            cursor.execute("""
                UPDATE delivery_promises
                SET promised_delivery_date = ?
                WHERE promise_id = ?
            """, (invalid_promise_date, promise_id))

            ground_truth_records.append({
                "anomaly_id": "ANOM-001",
                "edge_case_type": "PROMISE_BEFORE_ORDER_TIME",
                "entity_type": "delivery_promises",
                "entity_id": promise_id,
                "order_id": order_id,
                "injected_field": "promised_delivery_date",
                "injected_value": invalid_promise_date,
                "expected_valid_value": f">={order_date.isoformat()} (original: {original_promise})",
                "ground_truth_label": "ANOMALOUS_PROMISE_PRECEDES_ORDER",
                "severity": "CRITICAL",
                "description": "Delivery promise date occurs 2 days before the customer order was placed.",
                "created_at": INJECTION_TIMESTAMP,
            })

        # ---------------------------------------------------------------------
        # 2. Edge Case: Allocation exceeds stock
        # ---------------------------------------------------------------------
        line_candidate = cursor.execute("""
            SELECT ol.order_line_id, ol.order_id, ol.sku_id, sl.shipment_line_id,
                   sl.shipment_id, sl.allocated_quantity, s.node_id,
                   i.on_hand_quantity, i.inventory_id
            FROM order_lines ol
            JOIN shipment_lines sl ON sl.order_line_id = ol.order_line_id
            JOIN shipments s ON s.shipment_id = sl.shipment_id
            JOIN inventory i ON i.node_id = s.node_id AND i.sku_id = ol.sku_id
            ORDER BY ol.order_line_id DESC
            LIMIT 1
        """).fetchone()

        if line_candidate:
            line_id = line_candidate["order_line_id"]
            shipment_id = line_candidate["shipment_id"]
            shipment_line_id = line_candidate["shipment_line_id"]
            order_id = line_candidate["order_id"]
            orig_qty = line_candidate["allocated_quantity"]
            on_hand = line_candidate["on_hand_quantity"]

            excessive_quantity = on_hand + 50

            cursor.execute("""
                UPDATE shipment_lines
                SET allocated_quantity = ?
                WHERE shipment_line_id = ?
            """, (excessive_quantity, shipment_line_id))

            cursor.execute("""
                UPDATE allocation_decisions
                SET allocated_quantity = ?
                WHERE order_line_id = ?
            """, (excessive_quantity, line_id))

            exception_id = f"EXC-ANOM-{shipment_line_id}"
            cursor.execute("""
                INSERT OR REPLACE INTO allocation_exceptions (
                    exception_id, order_id, order_line_id, issue_type,
                    severity, unallocated_quantity, ground_truth_label, details, created_at
                )
                VALUES (?, ?, ?, 'ALLOCATION_EXCEEDS_STOCK', 'CRITICAL', ?, 'ALLOCATION_EXCEEDS_STOCK',
                        'Injected anomaly: allocated quantity exceeds total physical inventory.', ?)
            """, (exception_id, order_id, line_id, 50, INJECTION_TIMESTAMP))

            ground_truth_records.append({
                "anomaly_id": "ANOM-002",
                "edge_case_type": "ALLOCATION_EXCEEDS_STOCK",
                "entity_type": "shipment_lines",
                "entity_id": shipment_line_id,
                "order_id": order_id,
                "injected_field": "allocated_quantity",
                "injected_value": str(excessive_quantity),
                "expected_valid_value": f"<={on_hand} (original: {orig_qty})",
                "ground_truth_label": "ALLOCATION_EXCEEDS_STOCK",
                "severity": "CRITICAL",
                "description": f"Allocated quantity ({excessive_quantity}) violates physical on-hand inventory ({on_hand}).",
                "created_at": INJECTION_TIMESTAMP,
            })

        # ---------------------------------------------------------------------
        # 3. Edge Case: Carrier service unsupported for zone
        # ---------------------------------------------------------------------
        shipment_candidate = cursor.execute("""
            SELECT s.shipment_id, s.order_id, s.carrier_id, s.service_level_id, o.destination_zone_id
            FROM shipments s
            JOIN orders o ON o.order_id = s.order_id
            ORDER BY s.shipment_id DESC
            LIMIT 1
        """).fetchone()

        if shipment_candidate:
            shp_id = shipment_candidate["shipment_id"]
            order_id = shipment_candidate["order_id"]
            zone_id = shipment_candidate["destination_zone_id"]
            orig_carrier = shipment_candidate["carrier_id"]
            orig_service = shipment_candidate["service_level_id"]

            unsupported = cursor.execute("""
                SELECT c.carrier_id, sl.service_level_id
                FROM carriers c
                CROSS JOIN service_levels sl
                WHERE NOT EXISTS (
                    SELECT 1 FROM carrier_services cs
                    WHERE cs.carrier_id = c.carrier_id
                      AND cs.service_level_id = sl.service_level_id
                      AND cs.zone_id = ?
                )
                LIMIT 1
            """, (zone_id,)).fetchone()

            if unsupported:
                bad_carrier = unsupported["carrier_id"]
                bad_service = unsupported["service_level_id"]

                cursor.execute("""
                    UPDATE shipments
                    SET carrier_id = ?, service_level_id = ?
                    WHERE shipment_id = ?
                """, (bad_carrier, bad_service, shp_id))

                ground_truth_records.append({
                    "anomaly_id": "ANOM-003",
                    "edge_case_type": "CARRIER_SERVICE_UNSUPPORTED_FOR_ZONE",
                    "entity_type": "shipments",
                    "entity_id": shp_id,
                    "order_id": order_id,
                    "injected_field": "carrier_id / service_level_id",
                    "injected_value": f"{bad_carrier} + {bad_service}",
                    "expected_valid_value": f"Supported in carrier_services for {zone_id} (original: {orig_carrier} + {orig_service})",
                    "ground_truth_label": "CARRIER_SERVICE_UNSUPPORTED_FOR_ZONE",
                    "severity": "HIGH",
                    "description": f"Shipment assigned carrier {bad_carrier} and service {bad_service} which does not cover zone {zone_id}.",
                    "created_at": INJECTION_TIMESTAMP,
                })

        # ---------------------------------------------------------------------
        # 4. Edge Case: Shipment delivered before dispatch
        # ---------------------------------------------------------------------
        delivered_candidate = cursor.execute("""
            SELECT shipment_id, order_id, dispatched_at, delivered_at
            FROM shipments
            WHERE shipment_status = 'DELIVERED'
              AND dispatched_at IS NOT NULL
              AND delivered_at IS NOT NULL
            ORDER BY shipment_id DESC
            LIMIT 1
        """).fetchone()

        if delivered_candidate:
            shp_id = delivered_candidate["shipment_id"]
            order_id = delivered_candidate["order_id"]
            dispatched_at = delivered_candidate["dispatched_at"]
            original_delivered = delivered_candidate["delivered_at"]

            dispatch_dt = datetime.fromisoformat(dispatched_at)
            invalid_delivered = (dispatch_dt - timedelta(hours=4)).isoformat()

            cursor.execute("""
                UPDATE shipments
                SET delivered_at = ?
                WHERE shipment_id = ?
            """, (invalid_delivered, shp_id))

            cursor.execute("""
                UPDATE tracking_events
                SET event_time = ?
                WHERE shipment_id = ? AND event_code = 'DELIVERED'
            """, (invalid_delivered, shp_id))

            cursor.execute("""
                INSERT OR REPLACE INTO tracking_exceptions (
                    tracking_exception_id, shipment_id, issue_type,
                    severity, expected_delivery_date, actual_delivery_date,
                    details, created_at, exception_status
                )
                VALUES (?, ?, 'DELIVERY_FAILED', 'CRITICAL', ?, ?,
                        'Injected anomaly: package marked delivered prior to warehouse dispatch.', ?, 'OPEN')
            """, (f"TEX-{shp_id}-DELIV-BEFORE-DISP", shp_id, dispatched_at, invalid_delivered, INJECTION_TIMESTAMP))

            ground_truth_records.append({
                "anomaly_id": "ANOM-004",
                "edge_case_type": "SHIPMENT_DELIVERED_BEFORE_DISPATCH",
                "entity_type": "shipments",
                "entity_id": shp_id,
                "order_id": order_id,
                "injected_field": "delivered_at",
                "injected_value": invalid_delivered,
                "expected_valid_value": f">={dispatched_at} (original: {original_delivered})",
                "ground_truth_label": "DELIVERED_BEFORE_DISPATCH",
                "severity": "CRITICAL",
                "description": f"Shipment delivered timestamp ({invalid_delivered}) precedes its dispatch timestamp ({dispatched_at}).",
                "created_at": INJECTION_TIMESTAMP,
            })

        # ---------------------------------------------------------------------
        # 5. Edge Case: Split shipment status not rolled up correctly
        # ---------------------------------------------------------------------
        split_order = cursor.execute("""
            SELECT o.order_id, o.order_status, COUNT(s.shipment_id) as total_shipments
            FROM orders o
            JOIN shipments s ON s.order_id = o.order_id
            WHERE o.order_status = 'PARTIALLY_DELIVERED'
            GROUP BY o.order_id
            HAVING total_shipments > 1
            LIMIT 1
        """).fetchone()

        if not split_order:
            # Fallback to any order with multiple shipments
            split_order = cursor.execute("""
                SELECT o.order_id, o.order_status, COUNT(s.shipment_id) as total_shipments
                FROM orders o
                JOIN shipments s ON s.order_id = o.order_id
                GROUP BY o.order_id
                HAVING total_shipments > 1
                LIMIT 1
            """).fetchone()

        if split_order:
            order_id = split_order["order_id"]
            original_status = split_order["order_status"]

            # Corrupt status rollup: mark fully DELIVERED while split parts are not all delivered
            anomalous_status = "DELIVERED" if original_status != "DELIVERED" else "PARTIALLY_ALLOCATED"

            cursor.execute("""
                UPDATE orders
                SET order_status = ?
                WHERE order_id = ?
            """, (anomalous_status, order_id))

            cursor.execute("""
                INSERT INTO order_events (
                    order_event_id, order_id, previous_status, new_status, event_time, reason
                )
                VALUES (?, ?, ?, ?, ?, 'Injected split shipment status rollup anomaly')
            """, (f"OEV-ANOM-{order_id}", order_id, original_status, anomalous_status, INJECTION_TIMESTAMP))

            ground_truth_records.append({
                "anomaly_id": "ANOM-005",
                "edge_case_type": "SPLIT_SHIPMENT_STATUS_NOT_ROLLED_UP",
                "entity_type": "orders",
                "entity_id": order_id,
                "order_id": order_id,
                "injected_field": "order_status",
                "injected_value": anomalous_status,
                "expected_valid_value": original_status,
                "ground_truth_label": "SPLIT_SHIPMENT_STATUS_MISMATCH",
                "severity": "HIGH",
                "description": f"Split shipment order has status forced to '{anomalous_status}' when rollup derivation mandates '{original_status}'.",
                "created_at": INJECTION_TIMESTAMP,
            })

        connection.commit()

        # ---------------------------------------------------------------------
        # Save separate ground_truth.csv and ground_truth.json
        # ---------------------------------------------------------------------
        csv_path = GROUND_TRUTH_DIR / "ground_truth.csv"
        json_path = GROUND_TRUTH_DIR / "ground_truth.json"

        fieldnames = [
            "anomaly_id",
            "edge_case_type",
            "entity_type",
            "entity_id",
            "order_id",
            "injected_field",
            "injected_value",
            "expected_valid_value",
            "ground_truth_label",
            "severity",
            "description",
            "created_at",
        ]

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(ground_truth_records)

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(ground_truth_records, f, indent=4)

        print("\n" + "=" * 55)
        print("EDGE CASES INJECTED & GROUND TRUTH GENERATED")
        print("=" * 55)
        for rec in ground_truth_records:
            print(f"[{rec['anomaly_id']}] {rec['edge_case_type']} on {rec['entity_id']}: {rec['ground_truth_label']}")
        print(f"\nGround truth saved to:")
        print(f"- {csv_path}")
        print(f"- {json_path}")

        return ground_truth_records

    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    inject_edge_cases()
