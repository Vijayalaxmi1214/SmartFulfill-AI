
import random
from datetime import datetime, timedelta

from config.settings import RANDOM_SEED
from database.db_manager import get_connection


START_DATE = datetime(2026, 11, 15, 8, 0, 0)


def generate_orders(total_orders=100):
    rng = random.Random(RANDOM_SEED + 1)

    connection = get_connection()

    try:
        cursor = connection.cursor()

        skus = cursor.execute("""
            SELECT sku_id, unit_price
            FROM skus
            WHERE is_active = 1
            ORDER BY sku_id
        """).fetchall()

        zones = cursor.execute("""
            SELECT zone_id FROM service_zones
            ORDER BY zone_id
        """).fetchall()

        service_levels = cursor.execute("""
            SELECT service_level_id
            FROM service_levels
            ORDER BY service_level_id
        """).fetchall()

        if not skus or not zones or not service_levels:
            raise RuntimeError(
                "Master data missing. Generate master data first."
            )

        order_rows = []
        line_rows = []

        line_counter = 0

        for order_number in range(1, total_orders + 1):

            order_id = "ORD-2026-{0:06d}".format(order_number)

            customer_ref = "CUS-{0:06d}".format(
                rng.randint(1, 10000)
            )

            order_time = START_DATE + timedelta(
                days=rng.randint(0, 14),
                hours=rng.randint(0, 10),
                minutes=rng.randint(0, 59)
            )

            destination_zone = rng.choice(zones)[0]
            requested_service = rng.choice(service_levels)[0]

            order_rows.append((
                order_id,
                customer_ref,
                order_time.isoformat(),
                destination_zone,
                requested_service,
                "CREATED",
            ))

            # Every order contains 1 to 4 unique SKUs.
            line_count = rng.randint(1, 4)

            selected_skus = rng.sample(
                skus,
                min(line_count, len(skus))
            )

            for sku in selected_skus:
                line_counter += 1

                sku_id = sku["sku_id"]
                unit_price = sku["unit_price"]

                quantity = rng.randint(1, 5)

                order_line_id = "OLI-{0:08d}".format(
                    line_counter
                )

                line_rows.append((
                    order_line_id,
                    order_id,
                    sku_id,
                    quantity,
                    unit_price,
                ))

        cursor.executemany("""
            INSERT INTO orders (
                order_id,
                customer_ref,
                order_created_at,
                destination_zone_id,
                requested_service_level_id,
                order_status
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, order_rows)

        cursor.executemany("""
            INSERT INTO order_lines (
                order_line_id,
                order_id,
                sku_id,
                quantity,
                unit_price
            )
            VALUES (?, ?, ?, ?, ?)
        """, line_rows)

        connection.commit()

        print("\nORDER DATA GENERATED SUCCESSFULLY")
        print("Orders:", len(order_rows))
        print("Order lines:", len(line_rows))

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()
