
from datetime import datetime, timezone

from database.db_manager import get_connection


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def make_id(prefix, number):
    return "{}-{:08d}".format(prefix, number)


def allocate_orders():
    connection = get_connection()

    try:
        cursor = connection.cursor()

        orders = cursor.execute("""
            SELECT *
            FROM orders
            WHERE order_status = 'CREATED'
            ORDER BY order_created_at, order_id
        """).fetchall()

        if not orders:
            print("No CREATED orders available.")
            return

        inventory_rows = cursor.execute("""
            SELECT *
            FROM inventory
            ORDER BY node_id, sku_id
        """).fetchall()

        capacity_rows = cursor.execute("""
            SELECT *
            FROM warehouse_capacity
            ORDER BY node_id, capacity_date
        """).fetchall()

        inventory_map = {
            (r["node_id"], r["sku_id"]): {
                "inventory_id": r["inventory_id"],
                "available": (
                    r["on_hand_quantity"]
                    - r["reserved_quantity"]
                    - r["safety_stock"]
                )
            }
            for r in inventory_rows
        }

        capacity_map = {
            (r["node_id"], r["capacity_date"]): {
                "capacity_id": r["capacity_id"],
                "available": r["max_units"] - r["reserved_units"]
            }
            for r in capacity_rows
        }

        node_zones = cursor.execute("""
            SELECT node_id, zone_id
            FROM node_service_zones
            WHERE effective_from <= ?
              AND (effective_to IS NULL OR effective_to > ?)
        """, ("9999-12-31", "9999-12-31")).fetchall()

        # Build node -> supported zones.
        node_zone_map = {}

        for row in node_zones:
            node_zone_map.setdefault(row["node_id"], set()).add(
                row["zone_id"]
            )

        carrier_rows = cursor.execute("""
            SELECT carrier_id, service_level_id, zone_id
            FROM carrier_services
            WHERE effective_from <= ?
              AND (effective_to IS NULL OR effective_to > ?)
            ORDER BY carrier_id
        """, ("9999-12-31", "9999-12-31")).fetchall()

        carrier_map = {}

        for row in carrier_rows:
            key = (row["service_level_id"], row["zone_id"])
            carrier_map.setdefault(key, []).append(row["carrier_id"])

        lines_by_order = {}
        for line in cursor.execute("""
            SELECT * FROM order_lines ORDER BY order_id, order_line_id
        """).fetchall():
            lines_by_order.setdefault(line["order_id"], []).append(line)

        # Keep every allocation operation in one transaction.
        shipment_counter = 1
        decision_counter = 1
        exception_counter = 1
        order_event_counter = 1
        shipment_line_counter = 1
        inventory_event_counter = 1
        capacity_event_counter = 1

        shipment_groups = {}
        inventory_changes = []
        capacity_changes = []
        decision_rows = []
        exception_rows = []
        order_event_rows = []
        shipment_line_rows = []
        order_status_updates = []

        for order in orders:
            order_id = order["order_id"]
            zone_id = order["destination_zone_id"]
            service_id = order["requested_service_level_id"]
            order_date = order["order_created_at"][:10]

            lines = lines_by_order.get(order_id, [])

            order_requested = 0
            order_allocated = 0

            for line in lines:
                line_id = line["order_line_id"]
                sku_id = line["sku_id"]
                requested = line["quantity"]

                order_requested += requested
                remaining = requested

                eligible_carriers = carrier_map.get(
                    (service_id, zone_id), []
                )

                candidates = []

                if eligible_carriers:
                    for node_id, zones in node_zone_map.items():

                        if zone_id not in zones:
                            continue

                        stock = inventory_map.get((node_id, sku_id))
                        capacity = capacity_map.get(
                            (node_id, order_date)
                        )

                        if not stock or not capacity:
                            continue

                        if stock["available"] <= 0:
                            continue

                        if capacity["available"] <= 0:
                            continue

                        candidates.append({
                            "node_id": node_id,
                            "stock": stock,
                            "capacity": capacity,
                            "carrier_id": eligible_carriers[0]
                        })

                # Prefer the node that can fulfill the largest share,
                # reducing split shipments where possible.
                candidates.sort(
                    key=lambda x: (
                        -min(
                            x["stock"]["available"],
                            x["capacity"]["available"]
                        ),
                        x["node_id"]
                    )
                )

                allocated_for_line = 0

                for candidate in candidates:
                    if remaining <= 0:
                        break

                    stock = candidate["stock"]
                    capacity = candidate["capacity"]

                    quantity = min(
                        remaining,
                        stock["available"],
                        capacity["available"]
                    )

                    if quantity <= 0:
                        continue

                    node_id = candidate["node_id"]
                    carrier_id = candidate["carrier_id"]

                    group_key = (
                        order_id,
                        node_id,
                        carrier_id,
                        service_id
                    )

                    if group_key not in shipment_groups:
                        shipment_id = "SHP-2026-{:06d}".format(
                            shipment_counter
                        )
                        shipment_counter += 1

                        shipment_groups[group_key] = {
                            "shipment_id": shipment_id,
                            "order_id": order_id,
                            "node_id": node_id,
                            "carrier_id": carrier_id,
                            "service_id": service_id,
                            "created_at": order["order_created_at"],
                            "lines": []
                        }

                    shipment_id = shipment_groups[group_key]["shipment_id"]

                    shipment_groups[group_key]["lines"].append(
                        (line_id, quantity)
                    )

                    shipment_line_rows.append((
                        "SHL-{:08d}".format(shipment_line_counter),
                        shipment_id,
                        line_id,
                        quantity
                    ))
                    shipment_line_counter += 1

                    before_stock = stock["available"]
                    before_capacity = capacity["available"]

                    stock["available"] -= quantity
                    capacity["available"] -= quantity

                    inventory_changes.append({
                        "inventory_id": stock["inventory_id"],
                        "shipment_id": shipment_id,
                        "delta": quantity,
                        "before": before_stock,
                        "after": stock["available"],
                        "event_time": order["order_created_at"]
                    })

                    capacity_changes.append({
                        "capacity_id": capacity["capacity_id"],
                        "shipment_id": shipment_id,
                        "delta": quantity,
                        "before": before_capacity,
                        "after": capacity["available"],
                        "event_time": order["order_created_at"]
                    })

                    remaining -= quantity
                    allocated_for_line += quantity

                    decision_rows.append((
                        make_id("ALC", decision_counter),
                        order_id,
                        line_id,
                        node_id,
                        requested,
                        quantity,
                        "ALLOCATED" if remaining == 0 else "PARTIAL",
                        "Eligible stock and capacity available",
                        order["order_created_at"]
                    ))
                    decision_counter += 1

                order_allocated += allocated_for_line

                if remaining > 0:
                    if not eligible_carriers:
                        issue = "UNSUPPORTED_CARRIER_SERVICE"
                        details = (
                            "No carrier supports the requested service "
                            "level and destination zone."
                        )
                    elif not candidates:
                        issue = "NO_ELIGIBLE_FULFILLMENT_NODE"
                        details = (
                            "No eligible node has both service-zone coverage, "
                            "inventory and capacity."
                        )
                    else:
                        issue = "INSUFFICIENT_INVENTORY_OR_CAPACITY"
                        details = (
                            "Eligible nodes could not cover the complete "
                            "requested quantity."
                        )

                    exception_rows.append((
                        make_id("EXC", exception_counter),
                        order_id,
                        line_id,
                        issue,
                        "HIGH",
                        remaining,
                        issue,
                        details,
                        order["order_created_at"]
                    ))
                    exception_counter += 1

                    if allocated_for_line == 0:
                        decision_rows.append((
                            make_id("ALC", decision_counter),
                            order_id,
                            line_id,
                            None,
                            requested,
                            0,
                            "REJECTED",
                            issue,
                            order["order_created_at"]
                        ))
                        decision_counter += 1

            # Derive order status from actual allocated quantities.
            if order_allocated == order_requested:
                new_status = "ALLOCATED"
            elif order_allocated > 0:
                new_status = "PARTIALLY_ALLOCATED"
            else:
                new_status = "UNFULFILLED"

            cursor.execute("""
                UPDATE orders
                SET order_status = ?
                WHERE order_id = ?
            """, (new_status, order_id))

            order_event_rows.append((
                make_id("OE", order_event_counter),
                order_id,
                "CREATED",
                new_status,
                order["order_created_at"],
                "Allocation engine completed"
            ))
            order_event_counter += 1

        # Insert shipments before inserting movement events referencing them.
        cursor.executemany("""
            INSERT INTO shipments (
                shipment_id, order_id, node_id,
                carrier_id, service_level_id,
                shipment_status, created_at
            )
            VALUES (?, ?, ?, ?, ?, 'ALLOCATED', ?)
        """, [
            (
                group["shipment_id"],
                group["order_id"],
                group["node_id"],
                group["carrier_id"],
                group["service_id"],
                group["created_at"]
            )
            for group in shipment_groups.values()
        ])

        cursor.executemany("""
            INSERT INTO shipment_lines (
                shipment_line_id, shipment_id,
                order_line_id, allocated_quantity
            )
            VALUES (?, ?, ?, ?)
        """, shipment_line_rows)

        # Persist reserved stock quantities.
        cursor.executemany("""
            UPDATE inventory
            SET reserved_quantity = reserved_quantity + ?
            WHERE inventory_id = ?
        """, [(c["delta"], c["inventory_id"]) for c in inventory_changes])

        cursor.executemany("""
            INSERT INTO inventory_events (
                inventory_event_id, inventory_id,
                shipment_id, event_type, quantity_delta,
                quantity_before, quantity_after, event_time
            )
            VALUES (?, ?, ?, 'RESERVE', ?, ?, ?, ?)
        """, [
            (
                make_id("IVE", inventory_event_counter + i),
                c["inventory_id"],
                c["shipment_id"],
                c["delta"],
                c["before"],
                c["after"],
                c["event_time"]
            )
            for i, c in enumerate(inventory_changes)
        ])

        # Persist reserved warehouse capacity.
        cursor.executemany("""
            UPDATE warehouse_capacity
            SET reserved_units = reserved_units + ?
            WHERE capacity_id = ?
        """, [(c["delta"], c["capacity_id"]) for c in capacity_changes])

        cursor.executemany("""
            INSERT INTO capacity_events (
                capacity_event_id, capacity_id,
                shipment_id, event_type, units_delta,
                units_before, units_after, event_time
            )
            VALUES (?, ?, ?, 'RESERVE', ?, ?, ?, ?)
        """, [
            (
                make_id("CPE", capacity_event_counter + i),
                c["capacity_id"],
                c["shipment_id"],
                c["delta"],
                c["before"],
                c["after"],
                c["event_time"]
            )
            for i, c in enumerate(capacity_changes)
        ])

        cursor.executemany("""
            INSERT INTO allocation_decisions (
                decision_id, order_id, order_line_id, node_id,
                requested_quantity, allocated_quantity,
                decision_status, reason, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, decision_rows)

        cursor.executemany("""
            INSERT INTO allocation_exceptions (
                exception_id, order_id, order_line_id,
                issue_type, severity, unallocated_quantity,
                ground_truth_label, details, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, exception_rows)

        cursor.executemany("""
            INSERT INTO order_events (
                order_event_id, order_id, previous_status,
                new_status, event_time, reason
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, order_event_rows)

        connection.commit()

        print("\nFULFILLMENT ALLOCATION COMPLETED")
        print("Orders processed:", len(orders))
        print("Shipments created:", len(shipment_groups))
        print("Shipment lines:", len(shipment_line_rows))
        print("Allocation decisions:", len(decision_rows))
        print("Exceptions:", len(exception_rows))
        print("Inventory movements:", len(inventory_changes))
        print("Capacity movements:", len(capacity_changes))

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()
