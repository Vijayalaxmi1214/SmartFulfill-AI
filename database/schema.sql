PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS skus (
    sku_id TEXT PRIMARY KEY,
    sku_name TEXT NOT NULL,
    category TEXT NOT NULL,
    unit_weight_kg REAL NOT NULL CHECK(unit_weight_kg > 0),
    unit_price REAL NOT NULL CHECK(unit_price >= 0),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1))
);

CREATE TABLE IF NOT EXISTS service_zones (
    zone_id TEXT PRIMARY KEY,
    zone_name TEXT NOT NULL UNIQUE,
    region TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS service_levels (
    service_level_id TEXT PRIMARY KEY,
    service_name TEXT NOT NULL UNIQUE,
    transit_business_days INTEGER NOT NULL CHECK(transit_business_days >= 0),
    priority INTEGER NOT NULL CHECK(priority >= 1)
);

CREATE TABLE IF NOT EXISTS fulfillment_nodes (
    node_id TEXT PRIMARY KEY,
    node_name TEXT NOT NULL,
    city TEXT NOT NULL,
    state TEXT NOT NULL,
    node_type TEXT NOT NULL CHECK(node_type IN ('WAREHOUSE', 'STORE')),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1))
);

CREATE TABLE IF NOT EXISTS carriers (
    carrier_id TEXT PRIMARY KEY,
    carrier_name TEXT NOT NULL UNIQUE,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1))
);

CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY,
    customer_ref TEXT NOT NULL,
    order_created_at TEXT NOT NULL,
    destination_zone_id TEXT NOT NULL,
    requested_service_level_id TEXT,
    order_status TEXT NOT NULL DEFAULT 'CREATED'
        CHECK(order_status IN ('CREATED', 'ALLOCATED', 'PARTIALLY_ALLOCATED',
        'UNFULFILLED', 'SHIPPED', 'PARTIALLY_DELIVERED', 'DELIVERED', 'CANCELLED')),
    FOREIGN KEY(destination_zone_id) REFERENCES service_zones(zone_id),
    FOREIGN KEY(requested_service_level_id) REFERENCES service_levels(service_level_id)
);

CREATE TABLE IF NOT EXISTS order_lines (
    order_line_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    sku_id TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK(quantity > 0),
    unit_price REAL NOT NULL CHECK(unit_price >= 0),
    FOREIGN KEY(order_id) REFERENCES orders(order_id),
    FOREIGN KEY(sku_id) REFERENCES skus(sku_id),
    UNIQUE(order_id, sku_id)
);

CREATE TABLE IF NOT EXISTS inventory (
    inventory_id TEXT PRIMARY KEY,
    node_id TEXT NOT NULL,
    sku_id TEXT NOT NULL,
    on_hand_quantity INTEGER NOT NULL CHECK(on_hand_quantity >= 0),
    reserved_quantity INTEGER NOT NULL DEFAULT 0 CHECK(reserved_quantity >= 0),
    safety_stock INTEGER NOT NULL DEFAULT 0 CHECK(safety_stock >= 0),
    effective_from TEXT NOT NULL,
    effective_to TEXT,
    CHECK(reserved_quantity <= on_hand_quantity),
    CHECK(effective_to IS NULL OR effective_to > effective_from),
    FOREIGN KEY(node_id) REFERENCES fulfillment_nodes(node_id),
    FOREIGN KEY(sku_id) REFERENCES skus(sku_id),
    UNIQUE(node_id, sku_id, effective_from)
);

CREATE TABLE IF NOT EXISTS warehouse_capacity (
    capacity_id TEXT PRIMARY KEY,
    node_id TEXT NOT NULL,
    capacity_date TEXT NOT NULL,
    max_units INTEGER NOT NULL CHECK(max_units >= 0),
    reserved_units INTEGER NOT NULL DEFAULT 0 CHECK(reserved_units >= 0),
    CHECK(reserved_units <= max_units),
    FOREIGN KEY(node_id) REFERENCES fulfillment_nodes(node_id),
    UNIQUE(node_id, capacity_date)
);

CREATE TABLE IF NOT EXISTS carrier_calendar (
    calendar_id TEXT PRIMARY KEY,
    carrier_id TEXT NOT NULL,
    service_date TEXT NOT NULL,
    is_working_day INTEGER NOT NULL CHECK(is_working_day IN (0, 1)),
    cutoff_time TEXT NOT NULL,
    FOREIGN KEY(carrier_id) REFERENCES carriers(carrier_id),
    UNIQUE(carrier_id, service_date)
);

CREATE TABLE IF NOT EXISTS carrier_services (
    carrier_id TEXT NOT NULL,
    service_level_id TEXT NOT NULL,
    zone_id TEXT NOT NULL,
    effective_from TEXT NOT NULL,
    effective_to TEXT,
    PRIMARY KEY(carrier_id, service_level_id, zone_id, effective_from),
    CHECK(effective_to IS NULL OR effective_to > effective_from),
    FOREIGN KEY(carrier_id) REFERENCES carriers(carrier_id),
    FOREIGN KEY(service_level_id) REFERENCES service_levels(service_level_id),
    FOREIGN KEY(zone_id) REFERENCES service_zones(zone_id)
);

CREATE TABLE IF NOT EXISTS node_service_zones (
    node_id TEXT NOT NULL,
    zone_id TEXT NOT NULL,
    effective_from TEXT NOT NULL,
    effective_to TEXT,
    PRIMARY KEY(node_id, zone_id, effective_from),
    CHECK(effective_to IS NULL OR effective_to > effective_from),
    FOREIGN KEY(node_id) REFERENCES fulfillment_nodes(node_id),
    FOREIGN KEY(zone_id) REFERENCES service_zones(zone_id)
);

CREATE TABLE IF NOT EXISTS shipments (
    shipment_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    carrier_id TEXT NOT NULL,
    service_level_id TEXT NOT NULL,
    shipment_status TEXT NOT NULL DEFAULT 'CREATED'
        CHECK(shipment_status IN ('CREATED', 'ALLOCATED', 'DISPATCHED',
        'IN_TRANSIT', 'OUT_FOR_DELIVERY', 'DELIVERED', 'FAILED', 'CANCELLED')),
    created_at TEXT NOT NULL,
    dispatched_at TEXT,
    delivered_at TEXT,
    FOREIGN KEY(order_id) REFERENCES orders(order_id),
    FOREIGN KEY(node_id) REFERENCES fulfillment_nodes(node_id),
    FOREIGN KEY(carrier_id) REFERENCES carriers(carrier_id),
    FOREIGN KEY(service_level_id) REFERENCES service_levels(service_level_id)
);

CREATE TABLE IF NOT EXISTS shipment_lines (
    shipment_line_id TEXT PRIMARY KEY,
    shipment_id TEXT NOT NULL,
    order_line_id TEXT NOT NULL,
    allocated_quantity INTEGER NOT NULL CHECK(allocated_quantity > 0),
    FOREIGN KEY(shipment_id) REFERENCES shipments(shipment_id),
    FOREIGN KEY(order_line_id) REFERENCES order_lines(order_line_id),
    UNIQUE(shipment_id, order_line_id)
);

CREATE TABLE IF NOT EXISTS tracking_events (
    tracking_event_id TEXT PRIMARY KEY,
    shipment_id TEXT NOT NULL,
    event_sequence INTEGER NOT NULL CHECK(event_sequence > 0),
    event_code TEXT NOT NULL CHECK(event_code IN ('LABEL_CREATED', 'PICKED_UP',
        'DISPATCHED', 'IN_TRANSIT', 'ARRIVED_AT_HUB', 'OUT_FOR_DELIVERY',
        'DELIVERED', 'DELIVERY_FAILED')),
    event_time TEXT NOT NULL,
    event_location TEXT,
    event_description TEXT,
    FOREIGN KEY(shipment_id) REFERENCES shipments(shipment_id),
    UNIQUE(shipment_id, event_sequence)
);

CREATE TABLE IF NOT EXISTS delivery_promises (
    promise_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    promise_version INTEGER NOT NULL CHECK(promise_version > 0),
    calculated_at TEXT NOT NULL,
    promised_delivery_date TEXT NOT NULL,
    promise_status TEXT NOT NULL DEFAULT 'ACTIVE'
        CHECK(promise_status IN ('ACTIVE', 'SUPERSEDED', 'FULFILLED')),
    FOREIGN KEY(order_id) REFERENCES orders(order_id),
    UNIQUE(order_id, promise_version)
);

CREATE TABLE IF NOT EXISTS order_events (
    order_event_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    previous_status TEXT,
    new_status TEXT NOT NULL,
    event_time TEXT NOT NULL,
    reason TEXT,
    FOREIGN KEY(order_id) REFERENCES orders(order_id)
);

CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(order_created_at);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(order_status);
CREATE INDEX IF NOT EXISTS idx_inventory_sku_node ON inventory(sku_id, node_id);
CREATE INDEX IF NOT EXISTS idx_shipments_order ON shipments(order_id);
CREATE INDEX IF NOT EXISTS idx_tracking_shipment ON tracking_events(shipment_id, event_sequence);
CREATE INDEX IF NOT EXISTS idx_promises_order ON delivery_promises(order_id, promise_version);
