import sqlite3

from config.settings import DATABASE_PATH, SCHEMA_PATH, BASE_DIR, create_directories

def get_connection():
    create_directories()
    connection = sqlite3.connect(str(DATABASE_PATH))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = NORMAL")
    connection.execute("PRAGMA cache_size = -65536")   # 64 MB page cache
    connection.execute("PRAGMA temp_store = MEMORY")
    connection.execute("PRAGMA mmap_size = 268435456") # 256 MB memory-mapped I/O
    return connection

def initialize_database():
    create_directories()
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError("Database schema not found: {}".format(SCHEMA_PATH))
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    connection = get_connection()
    try:
        connection.executescript(schema)
        for stage_sql in ("stage3_schema.sql", "stage4_schema.sql", "stage5_schema.sql"):
            stage_path = BASE_DIR / "database" / stage_sql
            if stage_path.exists():
                connection.executescript(stage_path.read_text(encoding="utf-8"))
        connection.commit()
        print("Database initialized successfully.")
        print("Database location:", DATABASE_PATH)
    finally:
        connection.close()

def validate_database():
    connection = get_connection()
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
        tables = connection.execute("""
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
        """).fetchall()
        return {
            "integrity": integrity,
            "foreign_key_errors": len(foreign_key_errors),
            "tables": [row["name"] for row in tables],
        }
    finally:
        connection.close()

def get_table_count(table_name):
    allowed_tables = {
        "skus", "service_zones", "service_levels", "fulfillment_nodes",
        "carriers", "orders", "order_lines", "inventory", "warehouse_capacity",
        "carrier_calendar", "carrier_services", "node_service_zones", "shipments",
        "shipment_lines", "tracking_events", "delivery_promises", "order_events",
        "allocation_decisions", "allocation_exceptions", "inventory_events",
        "capacity_events", "holiday_calendar", "tracking_exceptions",
    }
    if table_name not in allowed_tables:
        raise ValueError("Unknown table name")
    connection = get_connection()
    try:
        return connection.execute(
            "SELECT COUNT(*) AS total FROM " + table_name
        ).fetchone()["total"]
    finally:
        connection.close()
