
import csv

from config.settings import GENERATED_DIR, create_directories
from database.db_manager import get_connection


EXPORT_TABLES = [
    "skus",
    "service_zones",
    "service_levels",
    "fulfillment_nodes",
    "carriers",
    "orders",
    "order_lines",
    "inventory",
    "warehouse_capacity",
    "carrier_calendar",
    "carrier_services",
    "node_service_zones",
    "holiday_calendar",
]


def export_all_tables():
    create_directories()

    connection = get_connection()

    try:
        for table in EXPORT_TABLES:

            cursor = connection.execute(
                "SELECT * FROM " + table
            )

            columns = [
                description[0]
                for description in cursor.description
            ]

            output_file = GENERATED_DIR / (table + ".csv")

            with open(
                output_file,
                "w",
                newline="",
                encoding="utf-8"
            ) as file:

                writer = csv.writer(file)
                writer.writerow(columns)

                for row in cursor:
                    writer.writerow(tuple(row))

            print("Exported:", output_file.name)

    finally:
        connection.close()
