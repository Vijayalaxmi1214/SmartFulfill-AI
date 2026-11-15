
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS allocation_decisions (
    decision_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    order_line_id TEXT NOT NULL,
    node_id TEXT,
    requested_quantity INTEGER NOT NULL CHECK(requested_quantity > 0),
    allocated_quantity INTEGER NOT NULL CHECK(allocated_quantity >= 0),
    decision_status TEXT NOT NULL CHECK(
        decision_status IN ('ALLOCATED', 'PARTIAL', 'REJECTED')
    ),
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(order_id) REFERENCES orders(order_id),
    FOREIGN KEY(order_line_id) REFERENCES order_lines(order_line_id),
    FOREIGN KEY(node_id) REFERENCES fulfillment_nodes(node_id)
);

CREATE TABLE IF NOT EXISTS inventory_events (
    inventory_event_id TEXT PRIMARY KEY,
    inventory_id TEXT NOT NULL,
    shipment_id TEXT,
    event_type TEXT NOT NULL,
    quantity_delta INTEGER NOT NULL,
    quantity_before INTEGER NOT NULL,
    quantity_after INTEGER NOT NULL,
    event_time TEXT NOT NULL,
    FOREIGN KEY(inventory_id) REFERENCES inventory(inventory_id),
    FOREIGN KEY(shipment_id) REFERENCES shipments(shipment_id)
);

CREATE TABLE IF NOT EXISTS capacity_events (
    capacity_event_id TEXT PRIMARY KEY,
    capacity_id TEXT NOT NULL,
    shipment_id TEXT,
    event_type TEXT NOT NULL,
    units_delta INTEGER NOT NULL,
    units_before INTEGER NOT NULL,
    units_after INTEGER NOT NULL,
    event_time TEXT NOT NULL,
    FOREIGN KEY(capacity_id) REFERENCES warehouse_capacity(capacity_id),
    FOREIGN KEY(shipment_id) REFERENCES shipments(shipment_id)
);

CREATE TABLE IF NOT EXISTS allocation_exceptions (
    exception_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    order_line_id TEXT NOT NULL,
    issue_type TEXT NOT NULL,
    severity TEXT NOT NULL CHECK(
        severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')
    ),
    unallocated_quantity INTEGER NOT NULL CHECK(unallocated_quantity > 0),
    ground_truth_label TEXT NOT NULL,
    details TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(order_id) REFERENCES orders(order_id),
    FOREIGN KEY(order_line_id) REFERENCES order_lines(order_line_id)
);

CREATE INDEX IF NOT EXISTS idx_allocation_order
ON allocation_decisions(order_id);

CREATE INDEX IF NOT EXISTS idx_allocation_node
ON allocation_decisions(node_id);

CREATE INDEX IF NOT EXISTS idx_exception_order
ON allocation_exceptions(order_id);

CREATE INDEX IF NOT EXISTS idx_inventory_events_inventory
ON inventory_events(inventory_id);

CREATE INDEX IF NOT EXISTS idx_capacity_events_capacity
ON capacity_events(capacity_id);
