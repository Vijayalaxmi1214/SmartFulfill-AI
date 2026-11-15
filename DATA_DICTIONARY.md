# SmartFulfill AI — Data Dictionary & Entity Specifications

## 1. Overview and Business Context
**SmartFulfill AI** is an intelligent order fulfillment and delivery promise optimization system. The platform selects fulfillment nodes and calculates delivery promise dates based on real-time inventory levels, warehouse processing capacity, carrier pickup cutoffs, and shipping service levels.

This data dictionary documents the **11 core entities** and their supporting relationship/event tables, defining column data types, nullability, allowed values/enums, physical units, uniqueness rules, cardinality, lifecycle states, and validation logic.

---

## 2. Entity-Relationship Summary & Cardinality

| Parent Entity | Relationship | Child Entity | Cardinality | Enforced Constraints / Bridge Table |
| :--- | :--- | :--- | :--- | :--- |
| `service_zones` | serves | `orders` | 1 : N | `orders.destination_zone_id` FK -> `service_zones.zone_id` |
| `service_levels` | requested by | `orders` | 1 : N | `orders.requested_service_level_id` FK -> `service_levels.service_level_id` |
| `orders` | contains | `order_lines` | 1 : N | Composite unique (`order_id`, `sku_id`) |
| `skus` | cataloged in | `order_lines` | 1 : N | `order_lines.sku_id` FK -> `skus.sku_id` |
| `fulfillment_nodes` | stocks | `inventory` | 1 : N | Composite unique (`node_id`, `sku_id`, `effective_from`) |
| `skus` | stored in | `inventory` | 1 : N | `inventory.sku_id` FK -> `skus.sku_id` |
| `fulfillment_nodes` | constrains | `warehouse_capacity`| 1 : N | Composite unique (`node_id`, `capacity_date`) |
| `carriers` | schedules | `carrier_calendar` | 1 : N | Composite unique (`carrier_id`, `service_date`) |
| `carriers` + `service_levels` + `service_zones` | connects | `carrier_services` | N : M : P | Bridge Table: PK (`carrier_id`, `service_level_id`, `zone_id`, `effective_from`) |
| `fulfillment_nodes` + `service_zones` | covers | `node_service_zones`| N : M | Bridge Table: PK (`node_id`, `zone_id`, `effective_from`) |
| `orders` | fulfilled by | `shipments` | 1 : N | `shipments.order_id` FK -> `orders.order_id` (Split Shipments) |
| `shipments` + `order_lines` | allocates | `shipment_lines` | N : M | Bridge Table: PK `shipment_line_id`, Unique (`shipment_id`, `order_line_id`) |
| `shipments` | emits | `tracking_events` | 1 : N | Composite unique (`shipment_id`, `event_sequence`) |
| `orders` | promised by | `delivery_promises` | 1 : N | Composite unique (`order_id`, `promise_version`) |
| `shipments` | alerts | `tracking_exceptions`| 1 : N | Composite unique (`shipment_id`, `issue_type`) |
| `orders` + `order_lines` | logs decisions| `allocation_decisions`| 1 : N | FK to `orders`, `order_lines`, and `fulfillment_nodes` |
| `orders` | audit trail | `order_events` | 1 : N | Immutable append-only audit trail |
| `inventory` | audit trail | `inventory_events` | 1 : N | Stock reservation/release movements |
| `warehouse_capacity`| audit trail | `capacity_events` | 1 : N | Daily fulfillment throughput consumption |

---

## 3. Data Dictionary for the 11 Core Entities

### 3.1 `orders`
Represents customer purchase orders requiring fulfillment.
- **Primary Key**: `order_id` (Text)
- **Lifecycle States**: `CREATED` -> `ALLOCATED` / `PARTIALLY_ALLOCATED` / `UNFULFILLED` -> `SHIPPED` -> `PARTIALLY_DELIVERED` -> `DELIVERED` / `CANCELLED`

| Field | Type | Required? | Allowed Values / Pattern | Units | Uniqueness | Validation Rule |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `order_id` | TEXT | Required | `^ORD-\d{4}-\d{6}$` | None | Primary Key | Zero-padded alphanumeric identifier |
| `customer_ref` | TEXT | Required | `^CUS-\d{6}$` | None | Non-unique | Valid customer identifier |
| `order_created_at`| TEXT | Required | ISO 8601 UTC timestamp | Time | Non-unique | Must be valid datetime string |
| `destination_zone_id` | TEXT | Required | Foreign Key | None | Non-unique | Must exist in `service_zones(zone_id)` |
| `requested_service_level_id` | TEXT | Optional | Foreign Key | None | Non-unique | Nullable or exists in `service_levels(service_level_id)` |
| `order_status` | TEXT | Required | `CREATED`, `ALLOCATED`, `PARTIALLY_ALLOCATED`, `UNFULFILLED`, `SHIPPED`, `PARTIALLY_DELIVERED`, `DELIVERED`, `CANCELLED` | None | Non-unique | Must follow valid lifecycle state machine |

---

### 3.2 `order_lines`
Specific SKUs and quantities requested in an order.
- **Primary Key**: `order_line_id` (Text)
- **Foreign Keys**: `order_id`, `sku_id`

| Field | Type | Required? | Allowed Values / Pattern | Units | Uniqueness | Validation Rule |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `order_line_id` | TEXT | Required | `^OLI-\d{8}$` | None | Primary Key | Monotonically increasing zero-padded ID |
| `order_id` | TEXT | Required | `^ORD-\d{4}-\d{6}$` | None | Non-unique | Must exist in `orders(order_id)` |
| `sku_id` | TEXT | Required | `^SKU-\d{5}$` | None | Non-unique | Must exist in `skus(sku_id)` |
| `quantity` | INTEGER | Required | `> 0` | Units | Non-unique | Must be integer >= 1 |
| `unit_price` | REAL | Required | `>= 0.0` | INR / Currency | Non-unique | Must equal `skus.unit_price` at order creation |

*Constraints*: `UNIQUE(order_id, sku_id)` prevents duplicate SKU line items per order.

---

### 3.3 `skus`
Product master catalog.
- **Primary Key**: `sku_id` (Text)

| Field | Type | Required? | Allowed Values / Pattern | Units | Uniqueness | Validation Rule |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `sku_id` | TEXT | Required | `^SKU-\d{5}$` | None | Primary Key | Immutable product ID |
| `sku_name` | TEXT | Required | Alphanumeric description | None | Non-unique | Non-empty string |
| `category` | TEXT | Required | `Electronics`, `Fashion`, `Home`, `Books`, `Sports`, `Accessories` | None | Non-unique | Predefined category enum |
| `unit_weight_kg` | REAL | Required | `> 0.0` | Kilograms (kg) | Non-unique | Must be strictly positive |
| `unit_price` | REAL | Required | `>= 0.0` | Currency | Non-unique | Non-negative price |
| `is_active` | INTEGER | Required | `0`, `1` | Boolean Flag | Non-unique | `1` for active items available for purchase |

---

### 3.4 `fulfillment_nodes`
Physical supply chain locations (warehouses, distribution centers, retail stores).
- **Primary Key**: `node_id` (Text)

| Field | Type | Required? | Allowed Values / Pattern | Units | Uniqueness | Validation Rule |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `node_id` | TEXT | Required | `^FUL-\d{4}-\d{6}$` | None | Primary Key | Standard node identifier |
| `node_name` | TEXT | Required | Descriptive name | None | Non-unique | Non-empty location title |
| `city` | TEXT | Required | Indian tier-1/tier-2 city | None | Non-unique | Predefined geographic city |
| `state` | TEXT | Required | Indian State / UT | None | Non-unique | Predefined province |
| `node_type` | TEXT | Required | `WAREHOUSE`, `STORE` | None | Non-unique | Facility categorization |
| `is_active` | INTEGER | Required | `0`, `1` | Boolean Flag | Non-unique | `1` indicates operational facility |

---

### 3.5 `inventory`
Stock positions for each SKU at each fulfillment facility.
- **Primary Key**: `inventory_id` (Text)
- **Foreign Keys**: `node_id`, `sku_id`

| Field | Type | Required? | Allowed Values / Pattern | Units | Uniqueness | Validation Rule |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `inventory_id` | TEXT | Required | `^INV-\d{7}$` | None | Primary Key | Stock record identifier |
| `node_id` | TEXT | Required | Foreign Key | None | Non-unique | Must exist in `fulfillment_nodes` |
| `sku_id` | TEXT | Required | Foreign Key | None | Non-unique | Must exist in `skus` |
| `on_hand_quantity` | INTEGER | Required | `>= 0` | Units | Non-unique | Total physical inventory present |
| `reserved_quantity`| INTEGER | Required | `>= 0` | Units | Non-unique | Allocated units awaiting dispatch |
| `safety_stock` | INTEGER | Required | `>= 0` | Units | Non-unique | Buffer stock unallocatable to standard orders |
| `effective_from` | TEXT | Required | ISO 8601 Date (`YYYY-MM-DD`) | Date | Non-unique | Start date of stock policy |
| `effective_to` | TEXT | Optional | ISO 8601 Date or NULL | Date | Non-unique | Must be NULL or `effective_to > effective_from` |

*Integrity Check*: `CHECK(reserved_quantity <= on_hand_quantity)`.
*Available Stock Formula*: `available = on_hand_quantity - reserved_quantity - safety_stock`.

---

### 3.6 `warehouse_capacity`
Daily throughput handling limit (pick, pack, ship units) for each facility.
- **Primary Key**: `capacity_id` (Text)
- **Foreign Key**: `node_id`

| Field | Type | Required? | Allowed Values / Pattern | Units | Uniqueness | Validation Rule |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `capacity_id` | TEXT | Required | `^CAP-\d{7}$` | None | Primary Key | Capacity record identifier |
| `node_id` | TEXT | Required | Foreign Key | None | Non-unique | Must exist in `fulfillment_nodes` |
| `capacity_date`| TEXT | Required | ISO 8601 Date (`YYYY-MM-DD`) | Date | Non-unique | Scheduled operational date |
| `max_units` | INTEGER | Required | `>= 0` | Units/Day | Non-unique | Maximum throughput capacity |
| `reserved_units` | INTEGER | Required | `>= 0` | Units/Day | Non-unique | Throughput consumed by allocations |

*Integrity Check*: `CHECK(reserved_units <= max_units)`.
*Constraint*: `UNIQUE(node_id, capacity_date)`.

---

### 3.7 `carriers`
Logistics and express parcel service providers.
- **Primary Key**: `carrier_id` (Text)

| Field | Type | Required? | Allowed Values / Pattern | Units | Uniqueness | Validation Rule |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `carrier_id` | TEXT | Required | `^CAR-\d{3}$` | None | Primary Key | Zero-padded carrier ID |
| `carrier_name` | TEXT | Required | BlueDart, Delhivery, DTDC, etc. | None | Unique | Distinct company name |
| `is_active` | INTEGER | Required | `0`, `1` | Boolean Flag | Non-unique | `1` indicates currently contracted |

---

### 3.8 `service_levels`
Service level agreements (SLA) for fulfillment speed.
- **Primary Key**: `service_level_id` (Text)

| Field | Type | Required? | Allowed Values / Pattern | Units | Uniqueness | Validation Rule |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `service_level_id` | TEXT | Required | `^SVC-\d{3}$` | None | Primary Key | SLA identifier |
| `service_name` | TEXT | Required | `STANDARD`, `EXPRESS`, `SAME_DAY` | None | Unique | Distinct SLA tier name |
| `transit_business_days`| INTEGER | Required | `>= 0` | Business Days | Non-unique | Days in transit excluding non-working days |
| `priority` | INTEGER | Required | `>= 1` | Priority Rank | Non-unique | 1 (highest priority) to 3 (standard) |

---

### 3.9 `shipments`
Physical shipments dispatched to fulfill orders (supports 1 order -> N split shipments).
- **Primary Key**: `shipment_id` (Text)
- **Lifecycle States**: `CREATED` -> `ALLOCATED` -> `DISPATCHED` -> `IN_TRANSIT` -> `OUT_FOR_DELIVERY` -> `DELIVERED` / `FAILED` / `CANCELLED`

| Field | Type | Required? | Allowed Values / Pattern | Units | Uniqueness | Validation Rule |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `shipment_id` | TEXT | Required | `^SHP-\d{4}-\d{6}$` | None | Primary Key | Unique shipment consignment number |
| `order_id` | TEXT | Required | Foreign Key | None | Non-unique | Must exist in `orders(order_id)` |
| `node_id` | TEXT | Required | Foreign Key | None | Non-unique | Must exist in `fulfillment_nodes(node_id)` |
| `carrier_id` | TEXT | Required | Foreign Key | None | Non-unique | Must exist in `carriers(carrier_id)` |
| `service_level_id`| TEXT | Required | Foreign Key | None | Non-unique | Must exist in `service_levels` |
| `shipment_status`| TEXT | Required | `CREATED`, `ALLOCATED`, `DISPATCHED`, `IN_TRANSIT`, `OUT_FOR_DELIVERY`, `DELIVERED`, `FAILED`, `CANCELLED` | None | Non-unique | Valid lifecycle state enum |
| `created_at` | TEXT | Required | ISO 8601 UTC timestamp | Time | Non-unique | Order allocation timestamp |
| `dispatched_at` | TEXT | Optional | ISO 8601 UTC timestamp | Time | Non-unique | Node dispatch timestamp; `>= created_at` |
| `delivered_at` | TEXT | Optional | ISO 8601 UTC timestamp | Time | Non-unique | Delivery timestamp; `>= dispatched_at` |

---

### 3.10 `tracking_events`
Sequential scan events recorded as packages move through the transit network.
- **Primary Key**: `tracking_event_id` (Text)
- **Foreign Key**: `shipment_id`

| Field | Type | Required? | Allowed Values / Pattern | Units | Uniqueness | Validation Rule |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `tracking_event_id`| TEXT | Required | `^TRK-SHP-\d{4}-\d{6}-\d{3}$` | None | Primary Key | Deterministic sequence identifier |
| `shipment_id` | TEXT | Required | Foreign Key | None | Non-unique | Must exist in `shipments(shipment_id)` |
| `event_sequence` | INTEGER | Required | `> 0` | Sequence Step | Non-unique | 1, 2, 3, ... chronological order |
| `event_code` | TEXT | Required | `LABEL_CREATED`, `PICKED_UP`, `DISPATCHED`, `IN_TRANSIT`, `ARRIVED_AT_HUB`, `OUT_FOR_DELIVERY`, `DELIVERED`, `DELIVERY_FAILED` | None | Non-unique | Permitted logistics status code |
| `event_time` | TEXT | Required | ISO 8601 UTC timestamp | Time | Non-unique | Strict chronological monotonicity |
| `event_location` | TEXT | Optional | Hub / Facility name | None | Non-unique | Descriptive scan site |
| `event_description`| TEXT | Optional | Status description | None | Non-unique | Contextual explanation |

*Constraint*: `UNIQUE(shipment_id, event_sequence)` ensures ordered execution per consignment.

---

### 3.11 `delivery_promises`
Guaranteed delivery dates calculated and promised to the customer.
- **Primary Key**: `promise_id` (Text)
- **Foreign Key**: `order_id`
- **Lifecycle States**: `ACTIVE` -> `SUPERSEDED` / `FULFILLED`

| Field | Type | Required? | Allowed Values / Pattern | Units | Uniqueness | Validation Rule |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `promise_id` | TEXT | Required | `^PROM-ORD-\d{4}-\d{6}-\d{2}$` | None | Primary Key | Format `PROM-<order-id>-<version>` |
| `order_id` | TEXT | Required | Foreign Key | None | Non-unique | Must exist in `orders(order_id)` |
| `promise_version` | INTEGER | Required | `>= 1` | Version # | Non-unique | Monotonically increments per re-calculation |
| `calculated_at` | TEXT | Required | ISO 8601 UTC timestamp | Time | Non-unique | Calculation instant |
| `promised_delivery_date` | TEXT | Required | ISO 8601 Date (`YYYY-MM-DD`) | Date | Non-unique | Promised delivery target; `>= order date` |
| `promise_status` | TEXT | Required | `ACTIVE`, `SUPERSEDED`, `FULFILLED` | None | Non-unique | Current validity status |

*Constraint*: `UNIQUE(order_id, promise_version)` guarantees immutable version audit trail.

---

## 4. Supporting & Anomaly / Ground Truth Entities

- `service_zones`: Geographic routing zones (`zone_id`, `zone_name`, `region`).
- `node_service_zones`: Bridge table defining which fulfillment nodes serve which destination zones.
- `carrier_services`: Bridge table declaring valid `(carrier_id, service_level_id, zone_id)` delivery corridors.
- `carrier_calendar`: Working days (`is_working_day IN (0,1)`) and pickup cutoffs (`cutoff_time`) per carrier and date.
- `holiday_calendar`: Public and bank holidays that pause carrier business-day transit calculation.
- `allocation_decisions`: Comprehensive decision logs explaining which facility fulfilled which order lines and why.
- `allocation_exceptions`: Unfulfillable quantities and stock/capacity exception records.
- `tracking_exceptions`: In-transit delivery exceptions (`DELIVERY_DELAYED`, `DELIVERY_FAILED`).
- `ground_truth`: Isolated ground-truth catalog detailing injected anomalies, expected behaviors, and evaluation labels.
