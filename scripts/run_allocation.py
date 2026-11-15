
from database.stage3_db import initialize_stage3_database
from generators.allocation_engine import allocate_orders
from database.db_manager import get_connection


def print_allocation_summary():
    connection = get_connection()

    try:
        cursor = connection.cursor()

        print("\n" + "=" * 50)
        print("SMARTFULFILL AI - ALLOCATION REPORT")
        print("=" * 50)

        queries = [
            ("Total orders", "SELECT COUNT(*) FROM orders"),
            ("Fully allocated", """
                SELECT COUNT(*) FROM orders
                WHERE order_status = 'ALLOCATED'
            """),
            ("Partially allocated", """
                SELECT COUNT(*) FROM orders
                WHERE order_status = 'PARTIALLY_ALLOCATED'
            """),
            ("Unfulfilled", """
                SELECT COUNT(*) FROM orders
                WHERE order_status = 'UNFULFILLED'
            """),
            ("Shipments", "SELECT COUNT(*) FROM shipments"),
            ("Shipment lines", "SELECT COUNT(*) FROM shipment_lines"),
            ("Allocation decisions", """
                SELECT COUNT(*) FROM allocation_decisions
            """),
            ("Exceptions", """
                SELECT COUNT(*) FROM allocation_exceptions
            """),
            ("Inventory events", """
                SELECT COUNT(*) FROM inventory_events
            """),
            ("Capacity events", """
                SELECT COUNT(*) FROM capacity_events
            """),
        ]

        for label, query in queries:
            value = cursor.execute(query).fetchone()[0]
            print("{:<27} {}".format(label + ":", value))

        print("\nORDER STATUS BREAKDOWN")

        rows = cursor.execute("""
            SELECT order_status, COUNT(*) AS total
            FROM orders
            GROUP BY order_status
            ORDER BY order_status
        """).fetchall()

        for row in rows:
            print("{:<27} {}".format(
                row["order_status"] + ":",
                row["total"]
            ))

        print("=" * 50)

    finally:
        connection.close()


def main():
    print("Initializing Stage 3 database...")
    initialize_stage3_database()

    print("\nRunning fulfillment allocation...")
    allocate_orders()

    print_allocation_summary()


if __name__ == "__main__":
    main()
