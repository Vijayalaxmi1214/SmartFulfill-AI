
from pathlib import Path
from datetime import datetime, date, timedelta
import argparse
import csv
import json

from database.db_manager import get_connection


ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = ROOT / "data" / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)


def parse_date(value):
    return date.fromisoformat(value[:10])


def active_on(start, end, target):
    start_date = parse_date(start)

    if start_date > target:
        return False

    if end and parse_date(end) < target:
        return False

    return True


def load_order(connection, order_id):

    order = connection.execute(
        """
        SELECT *
        FROM orders
        WHERE order_id = ?
        """,
        (order_id,),
    ).fetchone()

    if not order:
        raise ValueError(f"Order not found: {order_id}")

    lines = connection.execute(
        """
        SELECT
            ol.order_line_id,
            ol.sku_id,
            ol.quantity,
            ol.unit_price,
            s.sku_name,
            s.unit_weight_kg
        FROM order_lines ol
        JOIN skus s ON s.sku_id = ol.sku_id
        WHERE ol.order_id = ?
        ORDER BY ol.order_line_id
        """,
        (order_id,),
    ).fetchall()

    if not lines:
        raise ValueError("Order has no order lines.")

    return dict(order), [dict(line) for line in lines]


def get_service_level(connection, service_level_id):

    row = connection.execute(
        """
        SELECT *
        FROM service_levels
        WHERE service_level_id = ?
        """,
        (service_level_id,),
    ).fetchone()

    if not row:
        raise ValueError("Requested service level not found.")

    return dict(row)


def estimate_delivery(
    connection,
    carrier_id,
    order_datetime,
    transit_days,
):

    calendar_rows = connection.execute(
        """
        SELECT service_date, is_working_day, cutoff_time
        FROM carrier_calendar
        WHERE carrier_id = ?
          AND service_date >= ?
        ORDER BY service_date
        """,
        (carrier_id, order_datetime.date().isoformat()),
    ).fetchall()

    calendar = {
        row["service_date"]: dict(row)
        for row in calendar_rows
    }

    holidays = {
        row["holiday_date"]
        for row in connection.execute(
            """
            SELECT holiday_date
            FROM holiday_calendar
            WHERE is_active = 1
            """
        ).fetchall()
    }

    dispatch_date = None

    for offset in range(31):

        candidate = order_datetime.date() + timedelta(days=offset)
        key = candidate.isoformat()

        if candidate in [date.fromisoformat(h) for h in holidays]:
            continue

        row = calendar.get(key)

        if not row or not row["is_working_day"]:
            continue

        cutoff = datetime.strptime(
            row["cutoff_time"], "%H:%M"
        ).time()

        if offset == 0 and order_datetime.time() > cutoff:
            continue

        dispatch_date = candidate
        break

    if dispatch_date is None:
        return None, None

    delivery_date = dispatch_date
    remaining_days = int(transit_days)

    for offset in range(1, 61):

        if remaining_days == 0:
            break

        candidate = dispatch_date + timedelta(days=offset)
        key = candidate.isoformat()

        if candidate in [date.fromisoformat(h) for h in holidays]:
            continue

        row = calendar.get(key)

        if row and row["is_working_day"]:
            delivery_date = candidate
            remaining_days -= 1

    if remaining_days > 0:
        return dispatch_date, None

    return dispatch_date, delivery_date


def evaluate_node(
    connection,
    order,
    lines,
    node,
    order_datetime,
):

    reasons = []

    zone = connection.execute(
        """
        SELECT 1
        FROM node_service_zones
        WHERE node_id = ?
          AND zone_id = ?
          AND effective_from <= ?
          AND (effective_to IS NULL OR effective_to >= ?)
        LIMIT 1
        """,
        (
            node["node_id"],
            order["destination_zone_id"],
            order_datetime.date().isoformat(),
            order_datetime.date().isoformat(),
        ),
    ).fetchone()

    if not zone:
        return None, ["Warehouse does not serve destination zone."]

    total_units = sum(int(line["quantity"]) for line in lines)

    inventory_records = connection.execute(
        """
        SELECT sku_id, on_hand_quantity,
               reserved_quantity, safety_stock
        FROM inventory
        WHERE node_id = ?
          AND effective_from <= ?
          AND (effective_to IS NULL OR effective_to >= ?)
        """,
        (
            node["node_id"],
            order_datetime.date().isoformat(),
            order_datetime.date().isoformat(),
        ),
    ).fetchall()

    inventory = {
        row["sku_id"]: dict(row)
        for row in inventory_records
    }

    for line in lines:

        stock = inventory.get(line["sku_id"])

        if not stock:
            reasons.append(
                f"No inventory record for SKU {line['sku_id']}."
            )
            continue

        available = (
            stock["on_hand_quantity"]
            - stock["reserved_quantity"]
            - stock["safety_stock"]
        )

        if available < line["quantity"]:
            reasons.append(
                f"Insufficient stock for {line['sku_id']}: "
                f"available {available}, required {line['quantity']}."
            )

    if reasons:
        return None, reasons

    return {
        "total_units": total_units,
        "inventory_status": "AVAILABLE",
    }, []


def find_carriers(
    connection,
    order,
    service_level,
    order_datetime,
):

    rows = connection.execute(
        """
        SELECT
            c.carrier_id,
            c.carrier_name,
            cs.service_level_id,
            cs.zone_id
        FROM carrier_services cs
        JOIN carriers c
            ON c.carrier_id = cs.carrier_id
        WHERE c.is_active = 1
          AND cs.service_level_id = ?
          AND cs.zone_id = ?
          AND cs.effective_from <= ?
          AND (
              cs.effective_to IS NULL
              OR cs.effective_to >= ?
          )
        ORDER BY c.carrier_name
        """,
        (
            service_level["service_level_id"],
            order["destination_zone_id"],
            order_datetime.date().isoformat(),
            order_datetime.date().isoformat(),
        ),
    ).fetchall()

    return [dict(row) for row in rows]


def evaluate_order(order_id):

    connection = get_connection()

    try:

        order, lines = load_order(connection, order_id)

        order_datetime = datetime.fromisoformat(
            order["order_created_at"]
        )

        service = get_service_level(
            connection,
            order["requested_service_level_id"],
        )

        nodes = connection.execute(
            """
            SELECT *
            FROM fulfillment_nodes
            WHERE is_active = 1
            ORDER BY node_id
            """
        ).fetchall()

        candidates = []
        rejected = []

        for node_row in nodes:

            node = dict(node_row)

            inventory_result, reasons = evaluate_node(
                connection,
                order,
                lines,
                node,
                order_datetime,
            )

            if reasons:
                rejected.append({
                    "node_id": node["node_id"],
                    "node_name": node["node_name"],
                    "reasons": reasons,
                })
                continue

            carriers = find_carriers(
                connection,
                order,
                service,
                order_datetime,
            )

            if not carriers:

                rejected.append({
                    "node_id": node["node_id"],
                    "node_name": node["node_name"],
                    "reasons": [
                        "No active carrier supports the requested "
                        "service level and destination zone."
                    ],
                })
                continue

            for carrier in carriers:

                dispatch_date, delivery_date = estimate_delivery(
                    connection,
                    carrier["carrier_id"],
                    order_datetime,
                    service["transit_business_days"],
                )

                if not dispatch_date or not delivery_date:

                    rejected.append({
                        "node_id": node["node_id"],
                        "node_name": node["node_name"],
                        "carrier_id": carrier["carrier_id"],
                        "reasons": [
                            "No valid delivery date found in carrier calendar."
                        ],
                    })
                    continue

                capacity = connection.execute(
                    """
                    SELECT max_units, reserved_units
                    FROM warehouse_capacity
                    WHERE node_id = ?
                      AND capacity_date = ?
                    """,
                    (
                        node["node_id"],
                        dispatch_date.isoformat(),
                    ),
                ).fetchone()

                if not capacity:

                    rejected.append({
                        "node_id": node["node_id"],
                        "node_name": node["node_name"],
                        "carrier_id": carrier["carrier_id"],
                        "reasons": [
                            "No warehouse capacity record for dispatch date."
                        ],
                    })
                    continue

                available_capacity = (
                    capacity["max_units"]
                    - capacity["reserved_units"]
                )

                if available_capacity < inventory_result["total_units"]:

                    rejected.append({
                        "node_id": node["node_id"],
                        "node_name": node["node_name"],
                        "carrier_id": carrier["carrier_id"],
                        "reasons": [
                            "Insufficient warehouse capacity: "
                            f"available {available_capacity}, "
                            f"required {inventory_result['total_units']}."
                        ],
                    })
                    continue

                utilization = (
                    capacity["reserved_units"]
                    / capacity["max_units"] * 100
                    if capacity["max_units"] else 100
                )

                candidates.append({
                    "order_id": order_id,
                    "node_id": node["node_id"],
                    "node_name": node["node_name"],
                    "carrier_id": carrier["carrier_id"],
                    "carrier_name": carrier["carrier_name"],
                    "service_level": service["service_name"],
                    "destination_zone": order["destination_zone_id"],
                    "total_units": inventory_result["total_units"],
                    "dispatch_date": dispatch_date.isoformat(),
                    "estimated_delivery_date": delivery_date.isoformat(),
                    "capacity_utilization_before_allocation_pct": round(
                        utilization, 2
                    ),
                    "capacity_remaining_before_allocation": available_capacity,
                    "selection_basis": (
                        "Earliest estimated delivery date, then lower "
                        "warehouse capacity utilization, then stable ID order."
                    ),
                })

        # Deterministic ranking: earliest delivery first,
        # then lower existing capacity utilization.
        candidates.sort(
            key=lambda x: (
                x["estimated_delivery_date"],
                x["capacity_utilization_before_allocation_pct"],
                x["node_id"],
                x["carrier_id"],
            )
        )

        result = {
            "simulation_mode": True,
            "existing_data_modified": False,
            "order_id": order_id,
            "order_status": order["order_status"],
            "requested_service": service["service_name"],
            "feasible_plan_count": len(candidates),
            "rejected_option_count": len(rejected),
            "selected_plan": candidates[0] if candidates else None,
            "alternative_plans": candidates[1:],
            "rejected_options": rejected,
            "limitations": [
                "No carrier rate table exists; shipping cost is not scored.",
                "No warehouse-to-destination distance data exists.",
                "This simulation uses the current inventory and capacity snapshot.",
                "Existing orders have already been fulfilled; this is a what-if replay.",
                "The selected plan is a recommendation, not a new allocation."
            ],
        }

        output_file = REPORT_DIR / f"optimization_{order_id}.json"

        with open(output_file, "w", encoding="utf-8") as file:
            json.dump(result, file, indent=4)

        csv_file = REPORT_DIR / f"optimization_{order_id}.csv"

        with open(
            csv_file,
            "w",
            newline="",
            encoding="utf-8",
        ) as file:

            if candidates:
                writer = csv.DictWriter(
                    file,
                    fieldnames=list(candidates[0].keys()),
                )
                writer.writeheader()
                writer.writerows(candidates)

        print("\nSMARTFULFILL AI - OPTIMIZATION REPORT")
        print("=" * 60)
        print("Order:", order_id)
        print("Existing status:", order["order_status"])
        print("Simulation mode: ON")
        print("Feasible plans:", len(candidates))
        print("Rejected options:", len(rejected))

        if candidates:

            print("\nSELECTED FULFILLMENT PLAN")
            print("-" * 60)

            for key, value in candidates[0].items():
                print(f"{key}: {value}")

            print("\nALTERNATIVE PLANS")

            for candidate in candidates[1:6]:
                print(
                    candidate["node_name"],
                    "|",
                    candidate["carrier_name"],
                    "| Delivery:",
                    candidate["estimated_delivery_date"],
                )

        else:
            print("\nNo feasible fulfillment plan found.")

        print("\nREPORTS SAVED")
        print(output_file)
        print(csv_file)

        print("\nExisting database records were not modified.")

        return result

    finally:
        connection.close()


def main():

    parser = argparse.ArgumentParser(
        description="SmartFulfill AI What-if Fulfillment Optimizer"
    )

    parser.add_argument(
        "--order-id",
        help="Existing order ID to simulate",
    )

    args = parser.parse_args()

    if args.order_id:
        order_id = args.order_id

    else:

        connection = get_connection()

        try:
            row = connection.execute(
                """
                SELECT order_id
                FROM orders
                ORDER BY order_created_at DESC, order_id DESC
                LIMIT 1
                """
            ).fetchone()

            if not row:
                raise ValueError("No orders available.")

            order_id = row["order_id"]

        finally:
            connection.close()

    evaluate_order(order_id)


if __name__ == "__main__":
    main()
