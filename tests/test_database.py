from database.db_manager import initialize_database, validate_database, get_connection

def test_database_initialization():
    initialize_database()
    result = validate_database()
    assert result["integrity"] == "ok"
    assert result["foreign_key_errors"] == 0

def test_all_expected_tables_exist():
    initialize_database()
    result = validate_database()
    expected_tables = {
        "skus", "service_zones", "service_levels", "fulfillment_nodes",
        "carriers", "orders", "order_lines", "inventory", "warehouse_capacity",
        "carrier_calendar", "carrier_services", "node_service_zones", "shipments",
        "shipment_lines", "tracking_events", "delivery_promises", "order_events",
    }
    assert expected_tables.issubset(set(result["tables"]))

def test_foreign_key_enforcement():
    initialize_database()
    connection = get_connection()
    try:
        try:
            connection.execute("""
                INSERT INTO orders (
                    order_id, customer_ref, order_created_at, destination_zone_id
                ) VALUES (
                    'ORD-2026-999999', 'TEST-CUSTOMER',
                    '2026-11-15T10:00:00', 'INVALID-ZONE'
                )
            """)
            assert False, "Invalid foreign key was accepted"
        except Exception as error:
            assert "FOREIGN KEY" in str(error).upper()
    finally:
        connection.rollback()
        connection.close()
