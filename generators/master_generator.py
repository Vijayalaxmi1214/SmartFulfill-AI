import random
from datetime import date, timedelta

from config.settings import RANDOM_SEED
from database.db_manager import get_connection

START_DATE = date(2026, 11, 15)
CALENDAR_DAYS = 31

CITIES = (
    ("Hyderabad", "Telangana"),
    ("Warangal", "Telangana"),
    ("Vijayawada", "Andhra Pradesh"),
    ("Visakhapatnam", "Andhra Pradesh"),
    ("Bengaluru", "Karnataka"),
    ("Chennai", "Tamil Nadu"),
    ("Mumbai", "Maharashtra"),
    ("Pune", "Maharashtra"),
    ("Delhi", "Delhi"),
    ("Kolkata", "West Bengal"),
    ("Kochi", "Kerala"),
    ("Jaipur", "Rajasthan"),
    ("Ahmedabad", "Gujarat"),
    ("Lucknow", "Uttar Pradesh"),
    ("Bhopal", "Madhya Pradesh"),
    ("Nagpur", "Maharashtra"),
    ("Coimbatore", "Tamil Nadu"),
    ("Mysuru", "Karnataka"),
    ("Guntur", "Andhra Pradesh"),
    ("Nashik", "Maharashtra"),
)

CATEGORIES = (
    "Electronics",
    "Fashion",
    "Home",
    "Books",
    "Sports",
    "Accessories",
)

PRODUCTS = (
    "Laptop",
    "Smartphone",
    "Headphones",
    "Keyboard",
    "Mouse",
    "Monitor",
    "Tablet",
    "Smartwatch",
    "Backpack",
    "Shoes",
    "Book",
    "Camera",
)

CARRIERS = (
    "BlueDart",
    "Delhivery",
    "DTDC",
    "Ecom Express",
    "XpressBees",
    "India Post",
    "Shadowfax",
    "Ekart",
    "Amazon Shipping",
    "Professional Couriers",
)

SERVICE_LEVELS = (
    ("SVC-001", "STANDARD", 5, 3),
    ("SVC-002", "EXPRESS", 3, 2),
    ("SVC-003", "SAME_DAY", 0, 1),
)

ZONES = (
    ("ZON-001", "SOUTH-1", "South"),
    ("ZON-002", "SOUTH-2", "South"),
    ("ZON-003", "WEST-1", "West"),
    ("ZON-004", "WEST-2", "West"),
    ("ZON-005", "NORTH-1", "North"),
    ("ZON-006", "NORTH-2", "North"),
    ("ZON-007", "EAST-1", "East"),
    ("ZON-008", "EAST-2", "East"),
)


def reset_generated_tables(connection):
    """Clear existing generated data in child-first order."""
    tables = [
        "tracking_exceptions",
        "tracking_events",
        "shipment_lines",
        "inventory_events",
        "capacity_events",
        "delivery_promises",
        "allocation_exceptions",
        "allocation_decisions",
        "order_events",
        "shipments",
        "order_lines",
        "orders",
        "inventory",
        "warehouse_capacity",
        "carrier_calendar",
        "carrier_services",
        "node_service_zones",
        "carriers",
        "fulfillment_nodes",
        "service_levels",
        "service_zones",
        "skus",
    ]
    for table in tables:
        try:
            connection.execute("DELETE FROM " + table)
        except Exception:
            pass


def generate_zones(cursor):
    cursor.executemany(
        """
        INSERT INTO service_zones
        (zone_id, zone_name, region)
        VALUES (?, ?, ?)
        """,
        ZONES,
    )


def generate_service_levels(cursor):
    cursor.executemany(
        """
        INSERT INTO service_levels
        (service_level_id, service_name,
         transit_business_days, priority)
        VALUES (?, ?, ?, ?)
        """,
        SERVICE_LEVELS,
    )


def generate_nodes(cursor):
    nodes = []
    for index, (city, state) in enumerate(CITIES, start=1):
        node_id = "FUL-2026-{0:06d}".format(index)
        nodes.append((
            node_id,
            city + " Fulfillment Center",
            city,
            state,
            "WAREHOUSE" if index <= 12 else "STORE",
            1,
        ))
    cursor.executemany(
        """
        INSERT INTO fulfillment_nodes
        (node_id, node_name, city, state, node_type, is_active)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        nodes,
    )
    return [row[0] for row in nodes]


def generate_carriers(cursor):
    carriers = []
    for index, name in enumerate(CARRIERS, start=1):
        carriers.append((
            "CAR-{0:03d}".format(index),
            name,
            1,
        ))
    cursor.executemany(
        """
        INSERT INTO carriers
        (carrier_id, carrier_name, is_active)
        VALUES (?, ?, ?)
        """,
        carriers,
    )
    return [row[0] for row in carriers]


def generate_skus(cursor, rng):
    rows = []
    for index in range(1, 101):
        sku_id = "SKU-{0:05d}".format(index)
        product = rng.choice(PRODUCTS)
        category = rng.choice(CATEGORIES)
        rows.append((
            sku_id,
            product + " Model " + str(index),
            category,
            round(rng.uniform(0.1, 15.0), 2),
            round(rng.uniform(200, 100000), 2),
            1,
        ))
    cursor.executemany(
        """
        INSERT INTO skus
        (sku_id, sku_name, category, unit_weight_kg,
         unit_price, is_active)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    return [row[0] for row in rows]


def generate_inventory(cursor, rng, node_ids, sku_ids):
    rows = []
    for node_index, node_id in enumerate(node_ids, start=1):
        for sku_index, sku_id in enumerate(sku_ids, start=1):
            # 10% chance of stockout / unavailable inventory to trigger realistic exception paths
            if rng.random() < 0.10:
                on_hand = rng.randint(0, 3)
            else:
                on_hand = rng.randint(100, 260)
            reserved = rng.randint(0, on_hand // 5)
            safety = rng.randint(0, min(5, on_hand - reserved))
            inventory_id = "INV-{0:07d}".format(
                (node_index - 1) * len(sku_ids) + sku_index
            )
            rows.append((
                inventory_id,
                node_id,
                sku_id,
                on_hand,
                reserved,
                safety,
                START_DATE.isoformat(),
                None,
            ))
    cursor.executemany(
        """
        INSERT INTO inventory
        (inventory_id, node_id, sku_id,
         on_hand_quantity, reserved_quantity,
         safety_stock, effective_from, effective_to)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def generate_capacity(cursor, node_ids, rng):
    rows = []
    for node_index, node_id in enumerate(node_ids, start=1):
        for day_index in range(CALENDAR_DAYS):
            capacity_date = START_DATE + timedelta(days=day_index)
            # Tiered warehouse capacity: metro hubs have higher throughput
            if node_index <= 6:
                maximum = rng.randint(1000, 2000)
            else:
                maximum = rng.randint(400, 1000)
            reserved = rng.randint(0, maximum // 4)
            capacity_id = "CAP-{0:07d}".format(
                (node_index - 1) * CALENDAR_DAYS + day_index + 1
            )
            rows.append((
                capacity_id,
                node_id,
                capacity_date.isoformat(),
                maximum,
                reserved,
            ))
    cursor.executemany(
        """
        INSERT INTO warehouse_capacity
        (capacity_id, node_id, capacity_date,
         max_units, reserved_units)
        VALUES (?, ?, ?, ?, ?)
        """,
        rows,
    )


def generate_carrier_calendar(cursor, carrier_ids, rng):
    # Active holidays in Nov-Dec 2026 window
    holidays = {
        "2026-11-15", "2026-11-21", "2026-11-22", "2026-11-25",
        "2026-12-01", "2026-12-05", "2026-12-06", "2026-12-10",
        "2026-12-14", "2026-12-25"
    }
    rows = []
    for carrier_index, carrier_id in enumerate(carrier_ids, start=1):
        for day_index in range(CALENDAR_DAYS):
            service_date = START_DATE + timedelta(days=day_index)

            # Non-working if Sunday or holiday
            working = int(service_date.weekday() != 6 and service_date.isoformat() not in holidays)

            cutoff_hour = rng.choice([14, 15, 16, 17, 18])

            calendar_id = "CAL-{0:06d}".format(
                (carrier_index - 1) * CALENDAR_DAYS + day_index + 1
            )

            rows.append((
                calendar_id,
                carrier_id,
                service_date.isoformat(),
                working,
                "{0:02d}:00".format(cutoff_hour),
            ))

    cursor.executemany(
        """
        INSERT INTO carrier_calendar
        (calendar_id, carrier_id, service_date,
         is_working_day, cutoff_time)
        VALUES (?, ?, ?, ?, ?)
        """,
        rows,
    )


def generate_node_zones(cursor, node_ids):
    rows = []
    for index, node_id in enumerate(node_ids):
        # Each node serves three zones, with coverage distributed
        # across all eight zones.
        for offset in range(3):
            zone_index = (index + offset * 3) % len(ZONES)
            rows.append((
                node_id,
                ZONES[zone_index][0],
                START_DATE.isoformat(),
                None,
            ))

    cursor.executemany(
        """
        INSERT INTO node_service_zones
        (node_id, zone_id, effective_from, effective_to)
        VALUES (?, ?, ?, ?)
        """,
        rows,
    )


def generate_carrier_services(cursor, carrier_ids, rng):
    rows = []
    for carrier_id in carrier_ids:
        for service_id, _, _, _ in SERVICE_LEVELS:
            for zone_id, _, _ in ZONES:
                # Some carrier/zone/service combinations are
                # intentionally unsupported.
                if rng.random() < 0.75:
                    rows.append((
                        carrier_id,
                        service_id,
                        zone_id,
                        START_DATE.isoformat(),
                        None,
                    ))

    cursor.executemany(
        """
        INSERT INTO carrier_services
        (carrier_id, service_level_id, zone_id,
         effective_from, effective_to)
        VALUES (?, ?, ?, ?, ?)
        """,
        rows,
    )


def generate_holidays(cursor):
    """Populate holiday_calendar with Indian public holidays in Nov-Dec 2026."""
    holiday_rows = [
        ("HOL-001", "2026-11-15", "Guru Nanak Jayanti",          1),
        ("HOL-002", "2026-11-21", "Carrier Blackout - Peak",      1),
        ("HOL-003", "2026-11-22", "Carrier Blackout - Peak",      1),
        ("HOL-004", "2026-11-25", "Constitution Day (observ.)",   1),
        ("HOL-005", "2026-12-01", "Feast of St. Francis Xavier",  1),
        ("HOL-006", "2026-12-05", "Carrier Blackout - Sale",      1),
        ("HOL-007", "2026-12-06", "Dr. Ambedkar Mahaparinirvan", 1),
        ("HOL-008", "2026-12-10", "Human Rights Day",             1),
        ("HOL-009", "2026-12-14", "Carrier Blackout - Xmas",      1),
        ("HOL-010", "2026-12-25", "Christmas Day",                1),
    ]

    cursor.executemany(
        """
        INSERT OR IGNORE INTO holiday_calendar
            (holiday_id, holiday_date, holiday_name, is_active)
        VALUES (?, ?, ?, ?)
        """,
        holiday_rows,
    )

    return len(holiday_rows)


def generate_master_data():
    rng = random.Random(RANDOM_SEED)
    connection = get_connection()

    try:
        cursor = connection.cursor()

        reset_generated_tables(connection)

        generate_zones(cursor)
        generate_service_levels(cursor)

        node_ids = generate_nodes(cursor)
        carrier_ids = generate_carriers(cursor)
        sku_ids = generate_skus(cursor, rng)

        generate_inventory(cursor, rng, node_ids, sku_ids)
        generate_capacity(cursor, node_ids, rng)
        generate_carrier_calendar(cursor, carrier_ids, rng)
        generate_node_zones(cursor, node_ids)
        generate_carrier_services(cursor, carrier_ids, rng)

        holiday_count = generate_holidays(cursor)

        connection.commit()

        print("MASTER DATA GENERATED SUCCESSFULLY")
        print("SKUs:", len(sku_ids))
        print("Nodes:", len(node_ids))
        print("Carriers:", len(carrier_ids))
        print("Service zones:", len(ZONES))
        print("Service levels:", len(SERVICE_LEVELS))
        print("Holidays loaded:", holiday_count)

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()
