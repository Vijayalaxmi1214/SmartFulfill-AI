
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS tracking_exceptions (
    tracking_exception_id TEXT PRIMARY KEY,
    shipment_id TEXT NOT NULL,
    issue_type TEXT NOT NULL CHECK (
        issue_type IN (
            'DELIVERY_FAILED',
            'DELIVERY_DELAYED'
        )
    ),
    severity TEXT NOT NULL CHECK (
        severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')
    ),
    expected_delivery_date TEXT,
    actual_delivery_date TEXT,
    details TEXT NOT NULL,
    created_at TEXT NOT NULL,
    exception_status TEXT NOT NULL DEFAULT 'OPEN'
        CHECK(exception_status IN ('OPEN', 'RESOLVED')),
    FOREIGN KEY(shipment_id) REFERENCES shipments(shipment_id),
    UNIQUE(shipment_id, issue_type)
);

CREATE INDEX IF NOT EXISTS idx_tracking_exceptions_shipment
ON tracking_exceptions(shipment_id);

CREATE INDEX IF NOT EXISTS idx_tracking_exceptions_status
ON tracking_exceptions(exception_status);
