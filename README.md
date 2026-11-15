# SmartFulfill AI

**Intelligent Order Fulfillment and Delivery Promise Optimization System**

SmartFulfill AI selects fulfillment nodes and delivery promise dates using real-time inventory levels, warehouse processing capacity, carrier pickup cutoffs, and shipping service levels. It exposes key decisions and exceptions, preserves full historical audit traceability, and produces measurable operational metrics at enterprise scale.

---

## 1. Executive Summary & Full-Scale Benchmark

SmartFulfill AI is fully benchmarked and verified at full production volume:

| Entity / Dimension | Specification Target | Actual in Dataset | Status |
| :--- | :--- | :--- | :--- |
| **Customer Orders** | `50,000` | **50,000** (`ORD-2026-000001` – `ORD-2026-050000`) | 🟢 **100% Satisfied** |
| **Order Line Items** | Variable (1–4 per order) | **124,711** lines across 100 SKUs | 🟢 **Satisfied** |
| **Fulfillment Nodes** | `20` | **20** (`NOD-001` – `NOD-020` across 20 cities) | 🟢 **100% Satisfied** |
| **Logistics Carriers** | `10` | **10** (`CAR-001` – `CAR-010`) | 🟢 **100% Satisfied** |
| **Shipments Created** | Multi-node allocation | **51,988** shipments (`SHP-2026-000001` – `SHP-2026-051988`) | 🟢 **Satisfied** |
| **Tracking Events** | `100,000` | **353,518** chronological transit events | 🟢 **Exceeded (`3.5x`)** |
| **Split Shipments** | Required | **15,891** orders fulfilled from multiple nodes | 🟢 **Satisfied** |
| **Active Holidays** | Required | **10** public holidays & peak blackout dates | 🟢 **Satisfied** |
| **Capacity Constraints** | Required | **276** node-days reaching maximum handling capacity | 🟢 **Satisfied** |
| **Carrier Delays** | Required | **13,307** late shipments with tracking exceptions | 🟢 **Satisfied** |
| **Inventory Exceptions** | Required | **51,571** localized stockouts with fallback routing | 🟢 **Satisfied** |
| **Negative Edge Cases** | 5 Injected Scenarios | **5/5** detected and isolated in separate ground truth | 🟢 **100% Satisfied** |

---

## 2. Primary Actors & System Architecture

```
                                  CUSTOMER
                                     │ (Places Multi-line Order)
                                     ▼
                            [ Order Generator ]
                                     │
                                     ▼
                        [ Order Allocation Engine ]
                         ├── Checks Real-time Inventory (by Node & SKU)
                         ├── Checks Warehouse Daily Capacity Limits
                         └── Evaluates Carrier & Zone Coverage
                                     │
                    ┌────────────────┴────────────────┐
                    ▼                                 ▼
           [ Single Shipment ]               [ Split Shipments ]
         (1 Node Fulfills All)             (2+ Nodes Fulfill Lines)
                    │                                 │
                    └────────────────┬────────────────┘
                                     ▼
                      [ Delivery Promise Engine ]
                       ├── Carrier Operating Calendar (Working Days)
                       ├── Pickup Cutoff Times (e.g. 15:00, 18:00)
                       ├── Holiday & Blackout Day Blacklist
                       └── Service Level Transit Times (1-5 Days)
                                     │
                                     ▼
                        [ Tracking Simulation Engine ]
                         ├── Milestone Timeline (LABEL_CREATED -> DELIVERED)
                         ├── Injects Carrier In-transit Delays
                         └── Auto-Rolls Up Order-Level Lifecycle Status
                                     │
                                     ▼
                         [ AI Late-Delivery Model ]
                         ├── Evaluates In-transit Delay Probabilities
                         └── Generates Feature Importance & Mitigations
```

### Primary Actors & Roles
1. **Customer**: Places multi-line orders with requested delivery zones and service tiers (Standard, Express, Same-Day).
2. **Warehouse / Store Operator**: Manages physical inventory, safety stock thresholds, daily unit throughput, and carrier pickup cutoffs.
3. **Logistics & Operations Manager**: Supervises carrier SLA adherence, node capacity utilization, split-shipment costs, and transit exceptions.
4. **Merchandising & Supply Chain Analyst**: Inspects ML-driven delay risk scoring, feature importances, and what-if routing trade-offs.

---

## 3. 10-Step Specification Compliance Matrix

| Step | Requirement | Implementation in SmartFulfill AI |
| :--- | :--- | :--- |
| **Step 1** | Data Dictionary for 11 Core Entities | Documented in [`DATA_DICTIONARY.md`](DATA_DICTIONARY.md) with types, allowed enums, uniqueness constraints, foreign keys, and validation rules. |
| **Step 2** | Parent Master Data First, Then Transactions | Master generator creates catalog, nodes, carriers, calendars, and initial stock before order generation and downstream allocation. |
| **Step 3** | Deterministic ID Conventions | Strict zero-padded identifiers: `ORD-2026-000001`, `FUL-2026-000001`, `SHP-2026-000001`, `TRK-<shipment-id>-001`, `PROM-<order-id>-01`. |
| **Step 4** | Parameterized Scale & Fixed Seed | Deterministic seed `20261022`. Generation supports interactive runs (`--orders 100`) and the full enterprise baseline (`--orders 50000`). |
| **Step 5** | Inject 5 Labeled Edge Cases | `generators/edge_case_injector.py` injects 5 negative anomalies with precise `issue_type` and `ground_truth_label` tags. |
| **Step 6** | Derived Values from Source Records | Order status rollups, shipment promises, inventory movements, and capacity deltas are strictly calculated from source event logs. |
| **Step 7** | Separate Ground Truth File | Anomaly registry exported to [`data/ground_truth/ground_truth.csv`](data/ground_truth/ground_truth.csv) and `.json` without feature leakage. |
| **Step 8** | Multi-Point Validation Suite | 8-point validator (`scripts.validate_all`) verifies PKs, FKs, enums, chronological order, arithmetic reconciliation, and ground-truth parity. |
| **Step 9** | Seed Data Exports & Provenance Manifest | 23 database tables exported to CSV, SQL dump (`smartfulfill_seed.sql`), and cryptographic manifest (`source_manifest.json`). |
| **Step 10**| Reproducibility Demonstration | Verified via `scripts.verify_reproducibility` demonstrating identical row counts, state parity, and deterministic outputs. |

---

## 4. Injected Negative Scenarios & Ground Truth

The 5 required negative edge cases are intentionally injected to test auditing and automated validation:

| Anomaly ID | Edge Case Type | Target Entity | Injected Behavior | Ground Truth Label |
| :--- | :--- | :--- | :--- | :--- |
| **`ANOM-001`** | `PROMISE_BEFORE_ORDER_TIME` | `PROM-ORD-2026-049999-01` | Promised delivery date (`2026-11-15`) precedes order creation date (`2026-11-17`). | `ANOMALOUS_PROMISE_PRECEDES_ORDER` |
| **`ANOM-002`** | `ALLOCATION_EXCEEDS_STOCK` | `SHL-00023711` | Line allocated quantity (`293`) exceeds warehouse on-hand inventory (`243`). | `ALLOCATION_EXCEEDS_STOCK` |
| **`ANOM-003`** | `CARRIER_SERVICE_UNSUPPORTED_FOR_ZONE` | `SHP-2026-051988` | Shipment assigned carrier `CAR-001` for zone `ZON-007` which the carrier does not service. | `CARRIER_SERVICE_UNSUPPORTED_FOR_ZONE` |
| **`ANOM-004`** | `SHIPMENT_DELIVERED_BEFORE_DISPATCH` | `SHP-2026-051988` | Delivery timestamp (`11:52:00`) occurs before facility dispatch timestamp (`15:52:00`). | `DELIVERED_BEFORE_DISPATCH` |
| **`ANOM-005`** | `SPLIT_SHIPMENT_STATUS_NOT_ROLLED_UP` | `ORD-2026-000008` | Order marked `DELIVERED` despite only 1 of its 2 consignments having arrived. | `SPLIT_SHIPMENT_STATUS_MISMATCH` |

---

## 5. Machine Learning & Predictive Risk Pipeline

SmartFulfill AI trains a high-precision **Random Forest Classifier** to predict late delivery risk before arrival:

* **Training Population**: 41,591 completed shipments (28,284 on-time, 13,307 delayed).
* **Model Evaluation Metrics**:
  * **Accuracy**: `90.28%`
  * **Precision**: `100.0%` (Zero false-alarm late flags)
  * **Recall**: `69.61%`
  * **F1 Score**: `0.8208`
* **Active In-Transit Predictions**: 5,199 active consignments evaluated:
  * 🔴 High Risk (>70% probability): **1,171 shipments**
  * 🟡 Medium Risk (40–70% probability): **171 shipments**
  * 🟢 Low Risk (<40% probability): **3,857 shipments**
* **Top Explanatory Features**:
  1. `promise_lead_days` (Relative SLA buffer window)
  2. `order_created_weekday` (Weekend vs. weekday dispatch cutoffs)
  3. `order_created_hour` (Proximity to carrier pickup cutoffs)
  4. `node_id` & `destination_zone_id` (Distance & carrier zone compatibility)

---

## 6. Project Structure

```
SmartFulfill-AI/
├── app.py                            # Interactive Streamlit Command Center (7 Modules)
├── config/
│   └── settings.py                   # Paths, random seeds (20261022), SLA rules
├── database/
│   ├── db_manager.py                 # SQLite WAL mode connection pool & pragmas
│   ├── schema.sql                    # Core 16-table relational schema
│   ├── stage3_schema.sql             # Allocation decisions & movement events
│   ├── stage4_schema.sql             # Holiday calendar & delivery promises
│   └── stage5_schema.sql             # Tracking events & tracking exceptions
├── generators/
│   ├── master_generator.py           # Catalog, nodes, carriers, inventory, capacity, holidays
│   ├── order_generator.py            # Customer multi-line orders
│   ├── allocation_engine.py          # High-performance bulk fulfillment allocator
│   ├── delivery_promise_engine.py    # Calendar & cutoff-based SLA calculation
│   ├── tracking_engine.py            # Event milestone simulator & status rollups
│   ├── edge_case_injector.py         # Labeled negative anomaly injector
│   └── export_data.py                # CSV exporter
├── ml/
│   ├── prepare_training_data.py      # Leakage-safe feature extraction
│   ├── train_model.py                # Random Forest training & metric evaluation
│   ├── predict_risk.py               # Active shipment risk scoring
│   └── explain_model.py              # Permutation feature importance generator
├── optimization/
│   └── fulfillment_optimizer.py      # Multi-criteria scoring & policy trade-offs
├── scripts/
│   ├── generate_data.py              # Unified master data generator CLI
│   ├── validate_all.py               # 8-point comprehensive system validation
│   ├── validate_allocation.py        # Inventory & capacity boundary validator
│   ├── validate_promises.py          # SLA & promise chronology validator
│   ├── validate_tracking.py          # Event milestone & status consistency validator
│   ├── export_all.py                 # Full 23-table seed exporter & SQL dump
│   ├── spec_audit.py                 # Specification metric auditor
│   └── verify_reproducibility.py     # Deterministic fixed-seed verification
├── tests/
│   └── test_database.py              # Pytest relational integrity test suite
├── data/
│   ├── exports/                      # 23 CSV tables + smartfulfill_seed.sql
│   ├── ground_truth/                 # ground_truth.csv & ground_truth.json
│   ├── reports/                      # Risk predictions & feature importance
│   └── source_manifest.json          # SHA-256 cryptographic audit manifest
├── DATA_DICTIONARY.md                # Comprehensive data dictionary
└── README.md                         # This documentation
```

---

## 7. Step-by-Step Execution Guide

### Prerequisites
* Windows OS with PowerShell
* Python 3.10+ (Recommended via virtual environment)

```powershell
# 1. Activate virtual environment
.\.venv\Scripts\activate

# 2. Generate the full 50,000-order baseline with edge cases
python -m scripts.generate_data --orders 50000 --inject-edge-cases

# 3. Run the comprehensive system validation suite
python -m scripts.validate_all

# 4. Run individual domain validators
python -m scripts.validate_allocation
python -m scripts.validate_promises
python -m scripts.validate_tracking

# 5. Execute pytest test suite
python -m pytest tests -v

# 6. Train the AI Late Delivery Risk Model
python -m ml.prepare_training_data
python -m ml.train_model
python -m ml.predict_risk
python -m ml.explain_model

# 7. Export all seed tables, SQL dump, and cryptographic manifest
python -m scripts.export_all

# 8. Launch the interactive Streamlit command center (Port 8501)
streamlit run app.py --server.port 8501

# 9. (Optional) Launch FastAPI REST API server (Port 8000)
python run.py
```

---

## 8. Service Ports & Network Endpoints

| Service / Interface | Protocol | Port | Local URL | Network URL / Docs | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Streamlit Dashboard** | HTTP | **`8501`** | `http://localhost:8501` | `http://<your-ip>:8501` | Interactive Command Center (7 analytical modules, maps, optimizer, AI risk scoring) |
| **FastAPI REST API** | HTTP | **`8000`** | `http://127.0.0.1:8000` | `http://127.0.0.1:8000/docs` | Core backend REST API with OpenAPI/Swagger UI docs and schema verification |
| **FastAPI Health Endpoint** | HTTP | **`8000`** | `http://127.0.0.1:8000/health` | — | Microservice uptime, status, and UTC timestamp |
| **Database Status API** | HTTP | **`8000`** | `http://127.0.0.1:8000/database/status` | — | Real-time SQLite integrity check and 23-table status |
| **FastAPI ReDoc** | HTTP | **`8000`** | `http://127.0.0.1:8000/redoc` | — | Alternative technical documentation interface |

---

## 9. Interactive Streamlit Command Center (Port 8501)

The dashboard (`app.py`, running on **Port 8501**) provides 7 views:

1. **📊 Executive Control Tower & Network Overview**
   * High-level KPIs: Active consignments, on-time delivery rate (`67.5%`), total orders (`50,000`), and open exceptions.
   * Multi-select carrier and shipment status filtering.
2. **🏭 Fulfillment Nodes & Capacity Map**
   * Geographic overview of all 20 nodes with live capacity utilization gauges, stock levels, and facility tiers.
3. **📍 Interactive Tracking Event Stepper**
   * Consignment tracker visualizing milestone timestamps from pickup to final customer delivery.
4. **⚡ Multi-Criteria Fulfillment Optimizer & What-If Sandbox**
   * Interactive order simulation comparing *Earliest Delivery SLA*, *Lowest Capacity Utilization*, and *Carrier Reliability*.
   * Infeasibility breakdown chart detailing why rejected facilities were bypassed.
5. **🤖 AI Late Delivery Risk Predictor & Explainability**
   * Live prediction table with risk badges (High, Medium, Low) and feature importance rankings.
6. **⚠️ Exception Management & Ground-Truth Center**
   * Queue of tracking exceptions, stockouts, capacity alerts, and the 5 labeled ground-truth anomalies.
7. **📚 Relational Schema & Data Dictionary Viewer**
   * Direct inspection of the 23 relational database tables and foreign-key mappings.

---

## 10. FastAPI REST API Service (Port 8000)

Start the production REST microservice:
```powershell
python run.py
```
Or directly via Uvicorn:
```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Key endpoints:
* **Interactive OpenAPI Swagger Docs**: [`http://127.0.0.1:8000/docs`](http://127.0.0.1:8000/docs)
* **ReDoc Technical Specification**: [`http://127.0.0.1:8000/redoc`](http://127.0.0.1:8000/redoc)
* **Health & Readiness Probe**: [`http://127.0.0.1:8000/health`](http://127.0.0.1:8000/health)
* **Live Relational DB Health & Integrity**: [`http://127.0.0.1:8000/database/status`](http://127.0.0.1:8000/database/status)

---

## 11. Lawful Provenance & Data Ethics

This project uses **100% synthetically generated data** constructed from deterministic business rules, mathematical constraints, and supply chain logic:
* **Zero External PII**: No real-world customer names, phone numbers, or residential addresses are used.
* **Deterministic Reproducibility**: Using seed `20261022`, all tables, shipments, timestamps, and anomalies reproduce identically across environments.
* **Open Source License**: MIT License.
