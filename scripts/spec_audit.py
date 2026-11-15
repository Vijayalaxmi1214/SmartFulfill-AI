from database.db_manager import get_connection

conn = get_connection()
c = conn.cursor()

print("=== SPEC COMPLIANCE CHECK ===")
print("Orders:         ", c.execute("SELECT COUNT(*) FROM orders").fetchone()[0], "(need 50000)")
print("Nodes:          ", c.execute("SELECT COUNT(*) FROM fulfillment_nodes").fetchone()[0], "(need 20)")
print("Carriers:       ", c.execute("SELECT COUNT(*) FROM carriers").fetchone()[0], "(need 10)")
print("Tracking events:", c.execute("SELECT COUNT(*) FROM tracking_events").fetchone()[0], "(need 100000)")
print("Shipments:      ", c.execute("SELECT COUNT(*) FROM shipments").fetchone()[0])
print()

print("=== REQUIRED FEATURES ===")
r = c.execute("SELECT COUNT(*) FROM (SELECT order_id, COUNT(*) cnt FROM shipments GROUP BY order_id HAVING cnt>=2)").fetchone()[0]
print("Split shipments (orders with 2+ shipments):", r)
print()

print("Holidays in calendar:", c.execute("SELECT COUNT(*) FROM holiday_calendar WHERE is_active=1").fetchone()[0], "(need >0)")
print()

r = c.execute("SELECT COUNT(*) FROM warehouse_capacity WHERE reserved_units >= max_units").fetchone()[0]
print("Nodes at capacity:", r)
print()

r = c.execute("SELECT COUNT(*) FROM tracking_exceptions WHERE issue_type='DELIVERY_DELAYED'").fetchone()[0]
print("Delayed deliveries:", r)
print()

r = c.execute("SELECT COUNT(*) FROM allocation_exceptions").fetchone()[0]
print("Allocation exceptions (unavailable inventory):", r)
print()

print("=== TRACKING EVENTS BREAKDOWN ===")
for row in c.execute("SELECT event_code, COUNT(*) cnt FROM tracking_events GROUP BY event_code ORDER BY cnt DESC").fetchall():
    print(" ", row[0], ":", row[1])

print()
print("=== SHIPMENTS PER ORDER DISTRIBUTION ===")
for row in c.execute("SELECT cnt, COUNT(*) orders FROM (SELECT order_id, COUNT(*) cnt FROM shipments GROUP BY order_id) GROUP BY cnt ORDER BY cnt").fetchall():
    print("  Orders with", row[0], "shipment(s):", row[1])

conn.close()
