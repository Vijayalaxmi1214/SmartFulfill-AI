
from database.db_manager import get_connection

TABLES = [
    "orders",
    "order_lines",
    "fulfillment_nodes",
    "inventory",
    "warehouse_capacity",
    "service_levels",
    "node_service_zones",
    "carriers",
    "carrier_services",
    "carrier_calendar",
    "shipments",
    "shipment_lines",
]


def main():

    connection = get_connection()

    try:
        for table in TABLES:

            print("\n" + "=" * 70)
            print("TABLE:", table)
            print("=" * 70)

            count = connection.execute(
                f'SELECT COUNT(*) FROM "{table}"'
            ).fetchone()[0]

            print("Total records:", count)

            rows = connection.execute(
                f'SELECT * FROM "{table}" LIMIT 3'
            ).fetchall()

            columns = [
                column[1]
                for column in connection.execute(
                    f'PRAGMA table_info("{table}")'
                ).fetchall()
            ]

            for row in rows:
                print(dict(zip(columns, row)))

    finally:
        connection.close()


if __name__ == "__main__":
    main()
