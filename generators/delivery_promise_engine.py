
from datetime import datetime, date, timedelta, timezone

from database.db_manager import get_connection


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def next_working_day(calendar_cache, carrier_id, start_date, holidays):
    """Find the next eligible carrier operating date."""

    current = start_date

    for _ in range(60):
        row = calendar_cache.get((carrier_id, current.isoformat()))

        if (
            row
            and row["is_working_day"] == 1
            and current.isoformat() not in holidays
        ):
            return current

        current += timedelta(days=1)

    raise ValueError(
        "No working carrier date found within 60 days for "
        + carrier_id
    )


def calculate_dispatch_date(
    calendar_cache,
    carrier_id,
    ready_datetime,
    holidays
):
    """Apply the carrier's local pickup cutoff."""

    if ready_datetime.tzinfo is not None:
        ready_datetime = ready_datetime.replace(tzinfo=None)

    service_date = ready_datetime.date()

    row = calendar_cache.get((carrier_id, service_date.isoformat()))

    if (
        row
        and row["is_working_day"] == 1
        and service_date.isoformat() not in holidays
    ):
        cutoff = datetime.strptime(
            row["cutoff_time"], "%H:%M"
        ).time()

        if ready_datetime.time() <= cutoff:
            return service_date

    return next_working_day(
        calendar_cache,
        carrier_id,
        service_date + timedelta(days=1),
        holidays
    )


def add_transit_business_days(
    calendar_cache,
    carrier_id,
    dispatch_date,
    transit_days,
    holidays
):
    """Calculate delivery date using carrier working days."""

    delivery_date = dispatch_date
    days_added = 0

    while days_added < transit_days:
        delivery_date += timedelta(days=1)

        row = calendar_cache.get((carrier_id, delivery_date.isoformat()))

        if (
            row
            and row["is_working_day"] == 1
            and delivery_date.isoformat() not in holidays
        ):
            days_added += 1

        if (delivery_date - dispatch_date).days > 60:
            raise ValueError(
                "Delivery date calculation exceeded 60 days."
            )

    return delivery_date


def calculate_shipment_promise(
    calendar_cache,
    shipment,
    transit_days,
    holidays
):
    """Calculate the expected delivery date of one shipment."""

    if shipment["dispatched_at"]:
        dispatch_datetime = datetime.fromisoformat(
            shipment["dispatched_at"]
        )
        dispatch_date = dispatch_datetime.date()

        # A recorded dispatch must occur on a valid carrier day.
        calendar_row = calendar_cache.get(
            (shipment["carrier_id"], dispatch_date.isoformat())
        )

        if (
            not calendar_row
            or calendar_row["is_working_day"] != 1
            or dispatch_date.isoformat() in holidays
        ):
            raise ValueError(
                "Recorded dispatch is not on a valid carrier working day: "
                + shipment["shipment_id"]
            )

    else:
        ready_datetime = datetime.fromisoformat(
            shipment["created_at"]
        )

        dispatch_date = calculate_dispatch_date(
            calendar_cache,
            shipment["carrier_id"],
            ready_datetime,
            holidays
        )

    return add_transit_business_days(
        calendar_cache,
        shipment["carrier_id"],
        dispatch_date,
        transit_days,
        holidays
    )


def calculate_delivery_promises():
    connection = get_connection()

    try:
        cursor = connection.cursor()

        holidays = {
            row["holiday_date"]
            for row in cursor.execute("""
                SELECT holiday_date
                FROM holiday_calendar
                WHERE is_active = 1
            """).fetchall()
        }

        # Pre-load the entire carrier calendar into memory once
        # so that per-shipment lookups are O(1) dict gets.
        calendar_rows = cursor.execute("""
            SELECT carrier_id, service_date, is_working_day, cutoff_time
            FROM carrier_calendar
        """).fetchall()

        calendar_cache = {
            (row["carrier_id"], row["service_date"]): row
            for row in calendar_rows
        }

        shipments = cursor.execute("""
            SELECT
                s.shipment_id,
                s.order_id,
                s.carrier_id,
                s.service_level_id,
                s.created_at,
                s.dispatched_at,
                sl.transit_business_days
            FROM shipments s
            JOIN service_levels sl
                ON s.service_level_id = sl.service_level_id
            WHERE s.shipment_status = 'ALLOCATED'
            ORDER BY s.order_id, s.shipment_id
        """).fetchall()

        if not shipments:
            print("No allocated shipments found.")
            return

        # Group shipment promises by order.
        order_dates = {}
        order_created_map = {}
        shipment_results = {}

        for shipment in shipments:
            estimated_date = calculate_shipment_promise(
                calendar_cache,
                shipment,
                shipment["transit_business_days"],
                holidays
            )

            shipment_results[shipment["shipment_id"]] = (
                estimated_date.isoformat()
            )

            order_id = shipment["order_id"]
            order_created_map[order_id] = shipment["created_at"]

            order_dates.setdefault(order_id, []).append(
                estimated_date
            )

        promises_created = 0

        for order_id, dates in order_dates.items():

            calculated_at = order_created_map.get(order_id, "2026-11-15T08:00:00")

            # Complete-order promise = latest shipment date.
            promised_date = max(dates).isoformat()

            latest = cursor.execute("""
                SELECT MAX(promise_version) AS latest_version
                FROM delivery_promises
                WHERE order_id = ?
            """, (order_id,)).fetchone()

            version = (latest["latest_version"] or 0) + 1

            cursor.execute("""
                UPDATE delivery_promises
                SET promise_status = 'SUPERSEDED'
                WHERE order_id = ?
                  AND promise_status = 'ACTIVE'
            """, (order_id,))

            promise_id = "PROM-{}-{:02d}".format(
                order_id, version
            )

            cursor.execute("""
                INSERT INTO delivery_promises (
                    promise_id,
                    order_id,
                    promise_version,
                    calculated_at,
                    promised_delivery_date,
                    promise_status
                )
                VALUES (?, ?, ?, ?, ?, 'ACTIVE')
            """, (
                promise_id,
                order_id,
                version,
                calculated_at,
                promised_date
            ))

            promises_created += 1

        connection.commit()

        print("\nDELIVERY PROMISE CALCULATION COMPLETED")
        print("Shipments evaluated:", len(shipments))
        print("Order promises created:", promises_created)

        print("\nSAMPLE SHIPMENT DELIVERY DATES")

        for shipment_id, promised_date in list(
            shipment_results.items()
        )[:10]:
            print(shipment_id, "->", promised_date)

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()
