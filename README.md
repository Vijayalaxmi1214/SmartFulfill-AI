# SmartFulfill AI

**Intelligent Order Fulfillment and Delivery Promise Optimization System**

SmartFulfill AI selects fulfillment nodes and delivery promise dates using real-time inventory levels, warehouse processing capacity, carrier pickup cutoffs, and shipping service levels. It exposes key decisions and exceptions, preserves full historical traceability, and produces measurable operational metrics.

---

## 1. Primary Actors & Business Flow

1. **Customer**: Places multi-line orders with requested service levels (Standard, Express, Same-Day) and delivery zones.
2. **Warehouse / Store Operator**: Manages node-level physical on-hand inventory, daily handling capacity limits, and carrier pickup cutoffs.
3. **Operations Manager**: Monitors split-shipment fulfillment rates, SLA performance, carrier reliability, and transit bottlenecks.
4. **Merchandising / E-commerce Analyst**: Evaluates ML-driven late delivery risk predictions, permutation feature importance, and optimization trade-offs.

```
[Customer Order] ──> [Order Allocation Engine] ──> [Delivery Promise Engine]
                             │                                 │
              ┌──────────────┴──────────────┐                  ▼
              ▼                             ▼            [Shipment SLA]
     [Fulfillment Node 1]          [Fulfillment Node 2]        │
       (Inventory & Cap)             (Inventory & Cap)         ▼
              │                             │          [Tracking Engine]
              └──────────────┬──────────────┘                  │
                             ▼                                 ▼
                     [Carrier Routing] ─────────────> [Delivery Outcome]
```

---

## 2. Granular Steps & Specification Checklist

| Step | Requirement | Implementation in SmartFulfill AI |
| :--- | :--- | :--- |
| **Step 1** | Data Dictionary for 11 Core Entities | Detailed in [`DATA_DICTIONARY.md`](DATA_DICTIONARY.md) with types, uniqueness, validation rules, units, and lifecycle states. |
| **Step 2** | Parent Master Data First, Then Dependent Transactions | `master_generator.py` creates catalog, zones, carriers, nodes, inventory; `order_generator.py` and engines create downstream transactions. |
| **Step 3** | Deterministic ID Conventions | Standardized formats: `ORD-2026-000001`, `FUL-2026-000001`, `SHP-2026-000001`, `TRK-<shipment-id>-001`, `PROM-<order-id>-01`. |
| **Step 4** | Parameterized Scale & Fixed Seed | Fixed seed `20261022`. Default interactive volume (`--orders 100`) and parameterized full scale (`--orders 50000`). |
| **Step 5** | Inject 5 Labeled Edge Cases | `generators/edge_case_injector.py` injects: (1) Promise before order time; (2) Allocation exceeds stock; (3) Unsupported carrier zone; (4) Delivered before dispatch; (5) Split shipment status rollup mismatch. |
| **Step 6** | Derived Values from Source Records | Available stock, remaining capacity, transit SLA dates, and order status rollups are mathematically computed. |
| **Step 7** | Separate Ground Truth File | Anomaly catalog exported to `data/ground_truth/ground_truth.csv` and `data/ground_truth/ground_truth.json` (zero feature leakage). |
| **Step 8** | Multi-point Validation Suite | `python -m scripts.validate_all` tests PKs, FKs, enums, chronology, capacity bounds, rollup consistency, and ground truth reconciliation. |
| **Step 9** | Seed Exports & Source Manifest | `python -m scripts.export_all` generates CSVs, `smartfulfill_seed.sql`, and `data/source_manifest.json` with SHA-256 hashes. |
| **Step 10**| Reproducibility Demonstration | `python -m scripts.verify_reproducibility` regenerates twice with identical seed and proves 100% hash parity. |

---

## 3. Quick Start (Windows PowerShell)

### Setup Virtual Environment
```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

### Initialize Database
```powershell
python -m scripts.init_db
python -m scripts.validate_db
```

### Generate Baseline Dataset
```powershell
# Interactive baseline (100 orders, 220 shipments)
python -m scripts.generate_data --orders 100

# Or with the 5 labeled edge cases injected:
python -m scripts.generate_data --orders 100 --inject-edge-cases
```

### Run Validation Checks & Unit Tests
```powershell
# Run comprehensive multi-point validator
python -m scripts.validate_all

# Run pytest suite
python -m pytest tests -v
```

### Export Seed Data & Provenance Manifest
```powershell
python -m scripts.export_all
```

### Verify Fixed-Seed Reproducibility
```powershell
python -m scripts.verify_reproducibility
```

---

## 4. Machine Learning & Predictive Risk Pipeline

SmartFulfill AI includes an ML model that predicts late delivery risk for active in-transit shipments:

```powershell
# 1. Prepare training dataset (leakage-safe)
python -m ml.prepare_training_data

# 2. Train Random Forest model
python -m ml.train_model

# 3. Score active in-transit shipments
python -m ml.predict_risk

# 4. Compute permutation feature importance
python -m ml.explain_model
```

---

## 5. Multi-Criteria Fulfillment Optimizer

To evaluate and simulate optimal fulfillment node and carrier selection:
```powershell
python -m optimization.fulfillment_optimizer
```
Produces detailed trade-off analysis in `data/reports/optimization_*.json` and `*.csv`.

---

## 6. User Interfaces

### Interactive Streamlit Dashboard
```powershell
streamlit run app.py
```
- **Overview**: KPI metrics, delivery success rate, open exceptions, and status pie charts.
- **Shipment Analytics**: Complete consignment logs and export capabilities.
- **Exception Monitoring**: Severity and issue-type filterable operational queues.
- **Predictive AI**: Real-time delay risk probabilities for active shipments.
- **Model Explainability**: Model evaluation metrics (Precision, Recall, F1) and Permutation Feature Importance charts.

### FastAPI REST Service
```powershell
python run.py
```
- Health Check: `http://127.0.0.1:8000/health`
- Database Status: `http://127.0.0.1:8000/database/status`
- Interactive OpenAPI Docs: `http://127.0.0.1:8000/docs`

---

## 7. Lawful Provenance & Data Ethics

This project uses **100% synthetically generated data** constructed from deterministic business rules, mathematical constraints, and supply chain logic. No proprietary, confidential, personal, or externally scraped data is utilized.
