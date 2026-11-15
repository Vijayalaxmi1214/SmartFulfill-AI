
from datetime import datetime, timedelta

from database.db_manager import get_connection


def parse_datetime(value):
    return datetime.fromisoformat(value)


def format_datetime(value):
    return value.isoformat(timespec="seconds")


def event_id(shipment_id, sequence):
    return "TRK-{}-{:03d}".format(shipment_id, sequence)


def exception_id(shipment_id, issue_type):
    return "TEX-{}-{}".format(shipment_id, issue_type)


def simulated_outcome(shipment_id):
    """Generate deterministic shipment outcomes."""
    try:
        number = int(shipment_id.split("-")[-1])
    except (ValueError, IndexError):
        number = sum(ord(char) for char in shipment_id)

    remainder = number % 10

    if remainder == 0:
        return "FAILED"
    if remainder == 1:
        return "IN_TRANSIT"

    return "DELIVERED"


def build_events(shipment, promised_date):
    """Build chronological tracking events."""
    shipment_id = shipment["shipment_id"]
    created = parse_datetime(shipment["created_at"])

    picked_up = created + timedelta(hours=2)
    dispatched = created + timedelta(hours=4)
    in_transit = dispatched + timedelta(hours=12)
    arrived = dispatched + timedelta(days=1)
    out_for_delivery = arrived + timedelta(hours=2)

    outcome = simulated_outcome(shipment_id)

    events = [
        ("LABEL_CREATED", created, "Shipment registered"),
        ("PICKED_UP", picked_up, "Carrier picked up shipment"),
        ("DISPATCHED", dispatched, "Shipment left fulfillment node"),
        ("IN_TRANSIT", in_transit, "Shipment moving through carrier network"),
        ("ARRIVED_AT_HUB", arrived, "Shipment arrived at local hub"),
    ]

    if outcome == "IN_TRANSIT":
        return outcome, events, None

    events.append((
        "OUT_FOR_DELIVERY",
        out_for_delivery,
        "Shipment is out for customer delivery",
    ))

    if outcome == "FAILED":
        failed_time = out_for_delivery + timedelta(hours=3)

        events.append((
            "DELIVERY_FAILED",
            failed_time,
            "Delivery attempt failed in simulated tracking data",
        ))

        return outcome, events, None

    promised = datetime.combine(
        datetime.fromisoformat(promised_date).date(),
        datetime.min.time(),
    ) + timedelta(hours=12)

    try:
        number = int(shipment_id.split("-")[-1])
    except (ValueError, IndexError):
        number = sum(ord(char) for char in shipment_id)

    late_days = 2 if number % 5 == 0 else 0

    delivered_time = max(
        out_for_delivery + timedelta(hours=2),
        promised + timedelta(days=late_days),
    )

    events.append((
        "DELIVERED",
        delivered_time,
        "Shipment successfully delivered to customer",
    ))

    return outcome, events, delivered_time

def create_tracking_exception(
    connection,
    shipment_id,
    issue_type,
    severity,
    expected_date,
    actual_date,
    details,
    created_at=None,
):
    """Save tracking exceptions using the correct database columns."""

    exception_time = (
        created_at
        if created_at
        else (actual_date or expected_date or "2026-11-20T12:00:00")
    )

    cursor = connection.execute(
        """
        INSERT OR IGNORE INTO tracking_exceptions (
            tracking_exception_id,
            shipment_id,
            issue_type,
            severity,
            expected_delivery_date,
            actual_delivery_date,
            details,
            created_at,
            exception_status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'OPEN')
        """,
        (
            exception_id(shipment_id, issue_type),
            shipment_id,
            issue_type,
            severity,
            expected_date,
            actual_date,
            details,
            exception_time,
        ),
    )

    return cursor.rowcount


def insert_tracking_events(connection, shipment_id, events):
    """Insert chronological shipment tracking events."""

    inserted = 0

    for sequence, event in enumerate(events, start=1):
        event_code, event_time, description = event

        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO tracking_events (
                tracking_event_id,
                shipment_id,
                event_sequence,
                event_code,
                event_time,
                event_location,
                event_description
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id(shipment_id, sequence),
                shipment_id,
                sequence,
                event_code,
                format_datetime(event_time),
                "Synthetic Carrier Network",
                description,
            ),
        )

        inserted += cursor.rowcount

    return inserted


def update_shipment_status(
    connection,
    shipment_id,
    outcome,
    delivered_time,
    dispatched_time=None,
):
    """Update shipment status and timestamps."""

    if outcome == "DELIVERED":
        status = "DELIVERED"
    elif outcome == "FAILED":
        status = "FAILED"
    else:
        status = "IN_TRANSIT"

    shipment = connection.execute(
        """
        SELECT created_at, dispatched_at
        FROM shipments
        WHERE shipment_id = ?
        """,
        (shipment_id,),
    ).fetchone()

    if dispatched_time:
        dispatched_at = format_datetime(dispatched_time)
    elif shipment and shipment["dispatched_at"]:
        dispatched_at = shipment["dispatched_at"]
    elif shipment and shipment["created_at"]:
        dispatched_at = format_datetime(parse_datetime(shipment["created_at"]) + timedelta(hours=4))
    else:
        dispatched_at = "2026-11-15T12:00:00"

    delivered_at = (
        format_datetime(delivered_time)
        if delivered_time
        else None
    )

    connection.execute(
        """
        UPDATE shipments
        SET shipment_status = ?,
            dispatched_at = COALESCE(dispatched_at, ?),
            delivered_at = ?
        WHERE shipment_id = ?
        """,
        (status, dispatched_at, delivered_at, shipment_id),
    )
def backfill_tracking_exceptions(connection):
    """
    Find shipments delivered after their promised date
    and create missing DELIVERY_DELAYED exceptions.
    """

    rows = connection.execute(
        """
        SELECT
            s.shipment_id,
            dp.promised_delivery_date,
            s.delivered_at
        FROM shipments s
        JOIN (
            SELECT order_id, MAX(promise_version) AS latest_version
            FROM delivery_promises
            GROUP BY order_id
        ) latest
            ON latest.order_id = s.order_id
        JOIN delivery_promises dp
            ON dp.order_id = latest.order_id
            AND dp.promise_version = latest.latest_version
        WHERE s.shipment_status = 'DELIVERED'
          AND s.delivered_at IS NOT NULL
          AND DATE(s.delivered_at) > DATE(dp.promised_delivery_date)
        """
    ).fetchall()

    created = 0

    for row in rows:
        created += create_tracking_exception(
            connection=connection,
            shipment_id=row["shipment_id"],
            issue_type="DELIVERY_DELAYED",
            severity="HIGH",
            expected_date=row["promised_delivery_date"],
            actual_date=row["delivered_at"],
            details=(
                "Shipment was delivered after its promised "
                "delivery date. Delayed-delivery exception "
                "generated during tracking validation."
            ),
        )

    return created


def fulfill_delivery_promises(connection):
    """Mark an order promise fulfilled when all its shipments are delivered."""

    rows = connection.execute(
        """
        SELECT order_id
        FROM shipments
        GROUP BY order_id
        HAVING COUNT(*) > 0
           AND SUM(
               CASE
                   WHEN shipment_status = 'DELIVERED' THEN 1
                   ELSE 0
               END
           ) = COUNT(*)
        """
    ).fetchall()

    updated = 0

    for row in rows:
        cursor = connection.execute(
            """
            UPDATE delivery_promises
            SET promise_status = 'FULFILLED'
            WHERE order_id = ?
              AND promise_status = 'ACTIVE'
            """,
            (row["order_id"],),
        )

        updated += cursor.rowcount

    return updated


def update_order_statuses(connection):
    """Update order status based on shipment delivery progress."""

    rows = connection.execute(
        """
        SELECT
            order_id,
            COUNT(*) AS total_shipments,
            SUM(
                CASE
                    WHEN shipment_status = 'DELIVERED' THEN 1
                    ELSE 0
                END
            ) AS delivered_shipments,
            SUM(
                CASE
                    WHEN shipment_status = 'FAILED' THEN 1
                    ELSE 0
                END
            ) AS failed_shipments
        FROM shipments
        GROUP BY order_id
        """
    ).fetchall()

    updated = 0

    for row in rows:
        total = row["total_shipments"]
        delivered = row["delivered_shipments"] or 0
        failed = row["failed_shipments"] or 0

        if delivered == total:
            new_status = "DELIVERED"
        elif delivered > 0:
            new_status = "PARTIALLY_DELIVERED"
        elif failed == total:
            new_status = "CANCELLED"
        else:
            new_status = "SHIPPED"

        current = connection.execute(
            """
            SELECT order_status
            FROM orders
            WHERE order_id = ?
            """,
            (row["order_id"],),
        ).fetchone()

        if current is None or current["order_status"] == new_status:
            continue

        connection.execute(
            """
            UPDATE orders
            SET order_status = ?
            WHERE order_id = ?
            """,
            (new_status, row["order_id"]),
        )

        latest_event = connection.execute(
            """
            SELECT MAX(event_time) AS max_time
            FROM tracking_events te
            JOIN shipments s ON s.shipment_id = te.shipment_id
            WHERE s.order_id = ?
            """,
            (row["order_id"],),
        ).fetchone()

        status_event_time = (
            latest_event["max_time"]
            if latest_event and latest_event["max_time"]
            else "2026-11-20T12:00:00"
        )

        connection.execute(
            """
            INSERT OR IGNORE INTO order_events (
                order_event_id,
                order_id,
                previous_status,
                new_status,
                event_time,
                reason
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "OEV-TRACK-{}".format(row["order_id"]),
                row["order_id"],
                current["order_status"],
                new_status,
                status_event_time,
                "Order status updated from shipment tracking outcomes",
            ),
        )

        updated += 1

    return updated
def run_tracking_simulation():
    """Run shipment tracking and repair missing tracking exceptions."""

    connection = get_connection()

    try:
        shipments = connection.execute(
            """
            SELECT
                s.shipment_id,
                s.order_id,
                s.created_at,
                dp.promised_delivery_date
            FROM shipments s
            JOIN (
                SELECT order_id, MAX(promise_version) AS latest_version
                FROM delivery_promises
                GROUP BY order_id
            ) latest
                ON latest.order_id = s.order_id
            JOIN delivery_promises dp
                ON dp.order_id = latest.order_id
                AND dp.promise_version = latest.latest_version
            ORDER BY s.shipment_id
            """
        ).fetchall()

        evaluated = len(shipments)
        processed = 0
        delivered = 0
        failed = 0
        in_transit = 0
        late_deliveries = 0
        events_created = 0
        failed_exceptions = 0

        # Pre-fetch all shipment IDs that already have tracking events
        # (avoids N+1 SELECT COUNT(*) per shipment inside the loop).
        already_tracked = {
            row[0]
            for row in connection.execute(
                "SELECT DISTINCT shipment_id FROM tracking_events"
            ).fetchall()
        }

        # Collect all tracking event rows and shipment status updates
        # for bulk insertion rather than one INSERT per event.
        all_event_rows = []        # (tracking_event_id, shipment_id, seq, code, time, loc, desc)
        shipment_updates = []      # (outcome, delivered_time, dispatched_time, shipment_id)

        for shipment in shipments:
            # Do not duplicate tracking events on repeated runs.
            if shipment["shipment_id"] in already_tracked:
                continue

            outcome, events, delivered_time = build_events(
                shipment,
                shipment["promised_delivery_date"],
            )

            events_created += insert_tracking_events(
                connection,
                shipment["shipment_id"],
                events,
            )

            dispatched_time = events[2][1] if len(events) > 2 else None

            update_shipment_status(
                connection,
                shipment["shipment_id"],
                outcome,
                delivered_time,
                dispatched_time=dispatched_time,
            )

            processed += 1

            if outcome == "DELIVERED":
                delivered += 1

                promised = datetime.fromisoformat(
                    shipment["promised_delivery_date"]
                ).date()

                if delivered_time.date() > promised:
                    late_deliveries += 1

            elif outcome == "FAILED":
                failed += 1
                failed_exceptions += create_tracking_exception(
                    connection,
                    shipment["shipment_id"],
                    "DELIVERY_FAILED",
                    "HIGH",
                    shipment["promised_delivery_date"],
                    None,
                    "Simulated carrier delivery attempt failed.",
                )

            else:
                in_transit += 1

        # Repair delayed exceptions for shipments processed earlier.
        delayed_exceptions = backfill_tracking_exceptions(connection)

        orders_updated = update_order_statuses(connection)
        promises_fulfilled = fulfill_delivery_promises(connection)

        connection.commit()

        total_exceptions = failed_exceptions + delayed_exceptions

        print("\nSHIPMENT TRACKING COMPLETED")
        print("---------------------------")
        print("Shipments evaluated:", evaluated)
        print("New shipments processed:", processed)
        print("Delivered:", delivered)
        print("Failed:", failed)
        print("In transit:", in_transit)
        print("Late deliveries in this run:", late_deliveries)
        print("Tracking events created:", events_created)
        print("Failed exceptions created:", failed_exceptions)
        print("Delayed exceptions created:", delayed_exceptions)
        print("Total exceptions created in this run:", total_exceptions)
        print("Orders updated:", orders_updated)
        print("Promises fulfilled:", promises_fulfilled)

        print("\nSTAGE 5 EXECUTION COMPLETED")

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()