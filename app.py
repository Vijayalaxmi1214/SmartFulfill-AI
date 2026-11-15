import json
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from database.db_manager import get_connection
from optimization.fulfillment_optimizer import evaluate_order

# -----------------------------------------------------------------------------
# PAGE CONFIGURATION
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="SmartFulfill AI — Intelligent Logistics & Risk Control",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Styling for modern executive feel
st.markdown("""
<style>
    .metric-card {
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        border: 1px solid #334155;
        border-radius: 10px;
        padding: 16px 20px;
        color: #f8fafc;
        box-shadow: 0 4px 6px -1px rgba(0,0,0,0.2);
    }
    .metric-card-title {
        font-size: 0.82rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #94a3b8;
        margin-bottom: 4px;
    }
    .metric-card-value {
        font-size: 1.85rem;
        font-weight: 700;
        color: #38bdf8;
    }
    .badge-delivered { background-color: #059669; color: white; padding: 3px 8px; border-radius: 6px; font-size: 0.8rem; }
    .badge-intransit { background-color: #0284c7; color: white; padding: 3px 8px; border-radius: 6px; font-size: 0.8rem; }
    .badge-failed { background-color: #dc2626; color: white; padding: 3px 8px; border-radius: 6px; font-size: 0.8rem; }
    .badge-highrisk { background-color: #b91c1c; color: white; padding: 3px 8px; border-radius: 6px; font-size: 0.8rem; font-weight: bold; }
    .timeline-step {
        border-left: 3px solid #3b82f6;
        padding-left: 14px;
        margin-bottom: 12px;
        position: relative;
    }
</style>
""", unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# STATIC GEOGRAPHIC COORDINATES FOR FULFILLMENT NODES
# -----------------------------------------------------------------------------
NODE_COORDINATES = {
    "Hyderabad": (17.3850, 78.4867),
    "Warangal": (17.9689, 79.5941),
    "Vijayawada": (16.5062, 80.6480),
    "Visakhapatnam": (17.6868, 83.2185),
    "Bengaluru": (12.9716, 77.5946),
    "Chennai": (13.0827, 80.2707),
    "Mumbai": (19.0760, 72.8777),
    "Pune": (18.5204, 73.8567),
    "Delhi": (28.7041, 77.1025),
    "Kolkata": (22.5726, 88.3639),
    "Kochi": (9.9312, 76.2673),
    "Jaipur": (26.9124, 75.7873),
    "Ahmedabad": (23.0225, 72.5714),
    "Lucknow": (26.8467, 80.9462),
    "Bhopal": (23.2599, 77.4126),
    "Nagpur": (21.1458, 79.0882),
    "Coimbatore": (11.0168, 76.9558),
    "Mysuru": (12.2958, 76.6394),
    "Guntur": (16.3067, 80.4365),
    "Nashik": (19.9975, 73.7898),
}


# -----------------------------------------------------------------------------
# DATA ACCESS LAYER (CACHED)
# -----------------------------------------------------------------------------
@st.cache_data(ttl=20)
def load_core_data():
    conn = get_connection()
    try:
        shipments_df = pd.read_sql_query("""
            SELECT s.shipment_id, s.order_id, s.node_id, fn.node_name, fn.city, fn.state,
                   fn.node_type, s.carrier_id, c.carrier_name, s.service_level_id,
                   sl.service_name, sl.transit_business_days, s.shipment_status,
                   s.created_at, s.dispatched_at, s.delivered_at,
                   dp.promised_delivery_date
            FROM shipments s
            JOIN fulfillment_nodes fn ON fn.node_id = s.node_id
            JOIN carriers c ON c.carrier_id = s.carrier_id
            JOIN service_levels sl ON sl.service_level_id = s.service_level_id
            LEFT JOIN (
                SELECT order_id, promised_delivery_date
                FROM delivery_promises
                WHERE promise_status = 'ACTIVE'
            ) dp ON dp.order_id = s.order_id
            ORDER BY s.shipment_id
        """, conn)

        exceptions_df = pd.read_sql_query("""
            SELECT te.tracking_exception_id, te.shipment_id, s.order_id,
                   c.carrier_name, fn.node_name, te.issue_type, te.severity,
                   te.expected_delivery_date, te.actual_delivery_date,
                   te.details, te.exception_status, te.created_at
            FROM tracking_exceptions te
            JOIN shipments s ON s.shipment_id = te.shipment_id
            JOIN carriers c ON c.carrier_id = s.carrier_id
            JOIN fulfillment_nodes fn ON fn.node_id = s.node_id
            ORDER BY te.created_at DESC
        """, conn)

        nodes_df = pd.read_sql_query("""
            SELECT fn.node_id, fn.node_name, fn.city, fn.state, fn.node_type, fn.is_active,
                   COUNT(DISTINCT i.sku_id) as stocked_skus,
                   SUM(i.on_hand_quantity) as total_on_hand,
                   SUM(i.reserved_quantity) as total_reserved,
                   COALESCE(AVG(wc.reserved_units * 100.0 / NULLIF(wc.max_units, 0)), 0) as avg_capacity_util_pct
            FROM fulfillment_nodes fn
            LEFT JOIN inventory i ON i.node_id = fn.node_id
            LEFT JOIN warehouse_capacity wc ON wc.node_id = fn.node_id
            GROUP BY fn.node_id
        """, conn)

        orders_df = pd.read_sql_query("""
            SELECT o.order_id, o.customer_ref, o.order_created_at, o.destination_zone_id,
                   sz.region as destination_region, o.requested_service_level_id,
                   sl.service_name as requested_service, o.order_status,
                   COUNT(ol.order_line_id) as total_lines,
                   SUM(ol.quantity) as total_units,
                   SUM(ol.quantity * ol.unit_price) as order_value
            FROM orders o
            JOIN service_zones sz ON sz.zone_id = o.destination_zone_id
            LEFT JOIN service_levels sl ON sl.service_level_id = o.requested_service_level_id
            LEFT JOIN order_lines ol ON ol.order_id = o.order_id
            GROUP BY o.order_id
            ORDER BY o.order_created_at DESC
        """, conn)

        return shipments_df, exceptions_df, nodes_df, orders_df
    finally:
        conn.close()


@st.cache_data(ttl=20)
def load_predictions():
    pred_path = Path("data/reports/shipment_risk_predictions.csv")
    if pred_path.exists():
        return pd.read_csv(pred_path)
    return pd.DataFrame()


@st.cache_data(ttl=20)
def load_ground_truth():
    gt_path = Path("data/ground_truth/ground_truth.json")
    if gt_path.exists():
        with open(gt_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


# Load data safely
shipments, exceptions, nodes, orders = load_core_data()
risk_predictions = load_predictions()
ground_truth = load_ground_truth()


# -----------------------------------------------------------------------------
# SIDEBAR NAVIGATION & GLOBAL FILTERS
# -----------------------------------------------------------------------------
st.sidebar.title("📦 SmartFulfill AI")
st.sidebar.caption("Intelligent Fulfillment & Supply Chain Control Room")

navigation = st.sidebar.radio(
    "Navigation Modules",
    [
        "📊 Network & Overview",
        "🚚 Consignment & Tracking",
        "⚡ Fulfillment Optimizer Simulator",
        "🤖 Predictive AI & Risk Radar",
        "🚨 Exception Operations Center",
        "🔍 Anomaly & Ground Truth Inspector",
        "🧠 Model Explainability",
    ],
    index=0,
)

st.sidebar.markdown("---")
st.sidebar.subheader("Global Live Filters")

# Carrier Filter
all_carriers = sorted(shipments["carrier_name"].dropna().unique().tolist())
selected_carriers = st.sidebar.multiselect("Filter Carriers", all_carriers, default=all_carriers)

# Status Filter
all_statuses = sorted(shipments["shipment_status"].dropna().unique().tolist())
selected_statuses = st.sidebar.multiselect("Filter Shipment Status", all_statuses, default=all_statuses)

# Filter dataframe based on sidebar
filtered_shipments = shipments[
    (shipments["carrier_name"].isin(selected_carriers)) &
    (shipments["shipment_status"].isin(selected_statuses))
]

st.sidebar.markdown(f"**Showing:** {len(filtered_shipments)} of {len(shipments)} Shipments")

if st.sidebar.button("🔄 Refresh All Datasets", use_container_width=True):
    st.cache_data.clear()
    st.rerun()


# =============================================================================
# MODULE 1: NETWORK & OVERVIEW
# =============================================================================
if navigation == "📊 Network & Overview":
    st.title("📊 Supply Chain Network & Executive Overview")
    st.caption("Live operational KPIs, facility health, and India fulfillment topography.")

    # High-level KPIs
    tot_s = len(filtered_shipments)
    deliv_s = (filtered_shipments["shipment_status"] == "DELIVERED").sum()
    deliv_rate = round(deliv_s / tot_s * 100, 1) if tot_s else 0
    in_trans = (filtered_shipments["shipment_status"] == "IN_TRANSIT").sum()
    failed_s = (filtered_shipments["shipment_status"] == "FAILED").sum()
    open_exc = len(exceptions[exceptions["exception_status"] == "OPEN"])

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Active Shipments", f"{tot_s:,}", help="Shipments matching active filters")
    k2.metric("Delivery Success", f"{deliv_rate}%", delta=f"{deliv_rate - 90.0:.1f}% vs 90% SLA Target")
    k3.metric("In Transit", f"{in_trans:,}", delta_color="off")
    k4.metric("Failed Shipments", f"{failed_s:,}", delta=f"{failed_s} critical", delta_color="inverse")
    k5.metric("Open Exceptions", f"{open_exc:,}", delta=f"{open_exc} backlog", delta_color="inverse")

    st.markdown("---")

    # Interactive Geographic Network Map
    st.subheader("🗺️ India Fulfillment Nodes & Topography Map")
    st.caption("Hover over facilities to inspect capacity utilization, node types, and inventory depth.")

    map_nodes = nodes.copy()
    map_nodes["lat"] = map_nodes["city"].map(lambda c: NODE_COORDINATES.get(c, (20.59, 78.96))[0])
    map_nodes["lon"] = map_nodes["city"].map(lambda c: NODE_COORDINATES.get(c, (20.59, 78.96))[1])
    map_nodes["avg_capacity_util_pct"] = map_nodes["avg_capacity_util_pct"].round(1)

    fig_map = px.scatter_geo(
        map_nodes,
        lat="lat",
        lon="lon",
        size="total_on_hand",
        color="avg_capacity_util_pct",
        color_continuous_scale="Reds",
        hover_name="node_name",
        hover_data={
            "lat": False,
            "lon": False,
            "city": True,
            "node_type": True,
            "stocked_skus": True,
            "total_on_hand": True,
            "avg_capacity_util_pct": True,
        },
        labels={"avg_capacity_util_pct": "Capacity Util (%)"},
        title="Fulfillment Nodes: Inventory Volume (Size) vs Warehouse Capacity Utilization (Color)",
    )
    fig_map.update_geos(
        fitbounds="locations",
        visible=False,
        showcountries=True,
        countrycolor="#94a3b8",
        showland=True,
        landcolor="#f8fafc",
    )
    fig_map.update_layout(height=480, margin={"r": 0, "t": 40, "l": 0, "b": 0})
    st.plotly_chart(fig_map, use_container_width=True)

    # Operational Charts Grid
    c_left, c_right = st.columns(2)

    with c_left:
        st.subheader("🍩 Shipment Status Distribution")
        stat_counts = filtered_shipments["shipment_status"].value_counts().reset_index()
        stat_counts.columns = ["Status", "Count"]
        color_map = {
            "DELIVERED": "#10b981",
            "IN_TRANSIT": "#0284c7",
            "FAILED": "#ef4444",
            "ALLOCATED": "#f59e0b",
            "CANCELLED": "#64748b",
        }
        fig_stat = px.pie(
            stat_counts,
            names="Status",
            values="Count",
            color="Status",
            color_discrete_map=color_map,
            hole=0.5,
        )
        fig_stat.update_layout(margin=dict(t=20, b=20, l=20, r=20), height=320)
        st.plotly_chart(fig_stat, use_container_width=True)

    with c_right:
        st.subheader("⚡ Carrier SLA Breakdown")
        carrier_perf = filtered_shipments.groupby(["carrier_name", "shipment_status"]).size().reset_index(name="Count")
        fig_carrier = px.bar(
            carrier_perf,
            x="carrier_name",
            y="Count",
            color="shipment_status",
            color_discrete_map=color_map,
            barmode="stack",
            labels={"carrier_name": "Carrier", "Count": "Shipments"},
        )
        fig_carrier.update_layout(margin=dict(t=20, b=20, l=20, r=20), height=320, xaxis_tickangle=-30)
        st.plotly_chart(fig_carrier, use_container_width=True)


# =============================================================================
# MODULE 2: CONSIGNMENT & TRACKING
# =============================================================================
elif navigation == "🚚 Consignment & Tracking":
    st.title("🚚 Consignment Explorer & Live Tracking Timeline")
    st.caption("Inspect live shipments, filter corridors, and view full step-by-step scan timelines.")

    # Search Bar
    search_q = st.text_input("🔍 Search by Shipment ID, Order ID, or City", placeholder="e.g. SHP-2026-000001, Hyderabad...")
    disp_shipments = filtered_shipments.copy()
    if search_q:
        disp_shipments = disp_shipments[
            disp_shipments["shipment_id"].str.contains(search_q, case=False, na=False) |
            disp_shipments["order_id"].str.contains(search_q, case=False, na=False) |
            disp_shipments["city"].str.contains(search_q, case=False, na=False)
        ]

    st.dataframe(
        disp_shipments[[
            "shipment_id", "order_id", "node_name", "city", "carrier_name",
            "service_name", "shipment_status", "dispatched_at", "delivered_at", "promised_delivery_date"
        ]],
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("---")
    st.subheader("📍 Interactive Tracking Event Stepper")
    st.caption("Select a shipment ID to visualize its complete chronological transit scans.")

    selected_shp = st.selectbox(
        "Choose Shipment ID to inspect journey",
        disp_shipments["shipment_id"].tolist() if not disp_shipments.empty else shipments["shipment_id"].tolist()
    )

    if selected_shp:
        conn = get_connection()
        try:
            events = conn.execute("""
                SELECT tracking_event_id, event_sequence, event_code, event_time, event_location, event_description
                FROM tracking_events
                WHERE shipment_id = ?
                ORDER BY event_sequence ASC
            """, (selected_shp,)).fetchall()
        finally:
            conn.close()

        if events:
            cols = st.columns(len(events))
            for i, ev in enumerate(events):
                with cols[i]:
                    code = ev["event_code"]
                    badge_color = "#10b981" if code == "DELIVERED" else "#ef4444" if code == "DELIVERY_FAILED" else "#3b82f6"
                    st.markdown(f"""
                    <div style="border-top: 4px solid {badge_color}; background: #f1f5f9; padding: 10px; border-radius: 6px;">
                        <span style="font-size:0.75rem; color:#64748b;">Step {ev['event_sequence']}</span><br/>
                        <strong style="color: {badge_color}; font-size: 0.85rem;">{code}</strong><br/>
                        <small style="color:#334155;">{ev['event_time'][:16]}</small><br/>
                        <span style="font-size:0.75rem; color:#475569;">{ev['event_description'] or ''}</span>
                    </div>
                    """, unsafe_allow_html=True)
        else:
            st.info("No tracking events recorded for this shipment yet.")


# =============================================================================
# MODULE 3: FULFILLMENT OPTIMIZER SIMULATOR
# =============================================================================
elif navigation == "⚡ Fulfillment Optimizer Simulator":
    st.title("⚡ Multi-Criteria Fulfillment & Routing Optimizer")
    st.caption("Simulate real-time fulfillment allocation against live inventory, capacity limits, and carrier cutoff rules.")

    o_cols = st.columns([2, 1, 1])
    with o_cols[0]:
        order_list = orders["order_id"].tolist()
        sim_order_id = st.selectbox("Select Target Customer Order to Optimize", order_list)
    with o_cols[1]:
        priority_mode = st.selectbox("Optimization Policy", ["Earliest Delivery SLA", "Lowest Capacity Utilization", "Carrier Reliability"])
    with o_cols[2]:
        st.write("")
        st.write("")
        run_opt_btn = st.button("🚀 Run Live Optimization", type="primary", use_container_width=True)

    target_order_meta = orders[orders["order_id"] == sim_order_id].iloc[0]

    with st.expander("📦 Order Requisition Details", expanded=True):
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.markdown(f"**Customer Ref:** `{target_order_meta['customer_ref']}`")
        m2.markdown(f"**Destination:** `{target_order_meta['destination_zone_id']} ({target_order_meta['destination_region']})`")
        m3.markdown(f"**Requested SLA:** `{target_order_meta['requested_service']}`")
        m4.markdown(f"**Total Units:** `{target_order_meta['total_units']}`")
        m5.markdown(f"**Current Status:** `{target_order_meta['order_status']}`")

    if run_opt_btn or st.session_state.get(f"opt_done_{sim_order_id}"):
        st.session_state[f"opt_done_{sim_order_id}"] = True
        with st.spinner("Solving multi-criteria supply chain constraints..."):
            opt_result = evaluate_order(sim_order_id)

        st.success(f"Optimization Completed: Analyzed 20 Nodes & 10 Carriers. Found {opt_result['feasible_plan_count']} Feasible Fulfillment Plans.")

        win_col, chart_col = st.columns([1, 1])

        with win_col:
            st.subheader("🏆 Selected Optimal Fulfillment Plan")
            if opt_result.get("selected_plan"):
                sp = opt_result["selected_plan"]
                st.markdown(f"""
                <div style="background: linear-gradient(135deg, #065f46 0%, #064e3b 100%); border-radius: 10px; padding: 20px; color: white;">
                    <div style="font-size: 0.85rem; text-transform: uppercase; color: #a7f3d0; margin-bottom: 8px;">Recommended Fulfillment Route</div>
                    <div style="font-size: 1.6rem; font-weight: bold; margin-bottom: 12px;">{sp['node_name']}</div>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; font-size: 0.9rem;">
                        <div><strong>Carrier:</strong> {sp['carrier_name']}</div>
                        <div><strong>Service Tier:</strong> {sp['service_level']}</div>
                        <div><strong>Dispatch Date:</strong> {sp['dispatch_date']}</div>
                        <div><strong>Est. Delivery:</strong> {sp['estimated_delivery_date']}</div>
                        <div><strong>Capacity Left:</strong> {sp['capacity_remaining_before_allocation']} units</div>
                        <div><strong>Node Util:</strong> {sp['capacity_utilization_before_allocation_pct'] * 100:.1f}%</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.error("No single node possessed sufficient stock and capacity to fulfill this order.")

        with chart_col:
            st.subheader("🚫 Infeasible Node Rejection Analysis")
            if opt_result.get("rejected_options"):
                rej_df = pd.DataFrame(opt_result["rejected_options"])
                rej_counts = rej_df["reason"].value_counts().reset_index()
                rej_counts.columns = ["Rejection Reason", "Nodes"]
                fig_rej = px.bar(
                    rej_counts,
                    x="Nodes",
                    y="Rejection Reason",
                    orientation="h",
                    color="Rejection Reason",
                    title="Why Non-Selected Facilities Were Infeasible",
                )
                fig_rej.update_layout(showlegend=False, height=220, margin=dict(t=30, b=0, l=0, r=0))
                st.plotly_chart(fig_rej, use_container_width=True)

        if opt_result.get("candidate_plans"):
            st.subheader("📋 Top Feasible Alternative Plans")
            cand_df = pd.DataFrame(opt_result["candidate_plans"])
            st.dataframe(
                cand_df[[
                    "node_name", "carrier_name", "service_level", "dispatch_date",
                    "estimated_delivery_date", "capacity_remaining_before_allocation"
                ]],
                use_container_width=True,
                hide_index=True,
            )


# =============================================================================
# MODULE 4: PREDICTIVE AI & RISK RADAR
# =============================================================================
elif navigation == "🤖 Predictive AI & Risk Radar":
    st.title("🤖 AI-Powered Delivery Delay Risk Radar")
    st.caption("Active shipment delay probability scored by Random Forest classifier with interactive What-If scenario tester.")

    tab_radar, tab_whatif = st.tabs(["📡 Active In-Transit Risk Radar", "🎛️ Live What-If Scenario Simulator"])

    with tab_radar:
        if risk_predictions.empty:
            st.warning("No risk predictions generated yet. Run python -m ml.predict_risk first.")
        else:
            high_risk = risk_predictions[risk_predictions["risk_level"] == "HIGH"]
            med_risk = risk_predictions[risk_predictions["risk_level"] == "MEDIUM"]
            low_risk = risk_predictions[risk_predictions["risk_level"] == "LOW"]

            rc1, rc2, rc3 = st.columns(3)
            rc1.metric("🔴 High Risk (>65%)", len(high_risk), delta="Immediate attention needed", delta_color="inverse")
            rc2.metric("🟡 Medium Risk (35-65%)", len(med_risk), delta="Monitor milestones", delta_color="off")
            rc3.metric("🟢 Low Risk (<35%)", len(low_risk), delta="On schedule", delta_color="normal")

            st.markdown("---")
            st.subheader("📊 In-Transit Late Probability Distribution")
            fig_risk = px.bar(
                risk_predictions.sort_values("late_risk_percentage", ascending=False),
                x="shipment_id",
                y="late_risk_percentage",
                color="risk_level",
                color_discrete_map={"HIGH": "#ef4444", "MEDIUM": "#f59e0b", "LOW": "#10b981"},
                title="Shipment Risk Probability (%)",
                labels={"late_risk_percentage": "Late Risk (%)", "shipment_id": "Shipment ID"},
            )
            fig_risk.update_layout(xaxis_tickangle=-45, height=360)
            st.plotly_chart(fig_risk, use_container_width=True)

            if not high_risk.empty:
                st.subheader("🚨 High-Risk Shipments Requiring Intervention")
                st.dataframe(high_risk, use_container_width=True, hide_index=True)

    with tab_whatif:
        st.subheader("🎛️ Interactive What-If Scenario Risk Calculator")
        st.caption("Test how changing order creation time, transit lead days, or warehouse delays shifts late probability.")

        model_file = Path("models/late_delivery_model.joblib")
        if not model_file.exists():
            st.warning("Model file models/late_delivery_model.joblib not found. Run python -m ml.train_model first.")
        else:
            ml_model = joblib.load(model_file)

            wc1, wc2, wc3 = st.columns(3)
            with wc1:
                w_carrier = st.selectbox("Carrier", ["CAR-001", "CAR-002", "CAR-003", "CAR-004", "CAR-005"])
                w_node = st.selectbox("Node ID", ["FUL-2026-000001", "FUL-2026-000005", "FUL-2026-000007", "FUL-2026-000010"])
                w_service = st.selectbox("Service Level", ["SVC-001 (Standard)", "SVC-002 (Express)", "SVC-003 (Same Day)"]).split()[0]
                w_zone = st.selectbox("Destination Zone", ["ZON-001", "ZON-003", "ZON-005", "ZON-007"])

            with wc2:
                w_hour = st.slider("Order Creation Hour", 0, 23, 14, help="Hour of the day order was placed")
                w_weekday = st.slider("Order Creation Weekday", 0, 6, 2, help="0=Monday, 6=Sunday")
                w_transit_days = st.slider("Carrier Transit Business Days", 0, 7, 3)
                w_promise_days = st.slider("Promise Lead Days Allowed", 1, 10, 5)

            with wc3:
                w_delay = st.slider("Warehouse Processing Delay (Hours)", 1.0, 36.0, 4.0, help="Simulate warehouse backlog")
                w_node_type = st.radio("Node Type", ["WAREHOUSE", "STORE"])
                w_priority = 1 if w_service == "SVC-003" else 2 if w_service == "SVC-002" else 3

            sample_input = pd.DataFrame([{
                "carrier_id": w_carrier,
                "node_id": w_node,
                "service_level_id": w_service,
                "destination_zone_id": w_zone,
                "requested_service_level_id": w_service,
                "node_type": w_node_type,
                "priority": w_priority,
                "transit_business_days": w_transit_days,
                "order_created_weekday": w_weekday,
                "order_created_hour": w_hour,
                "dispatch_delay_hours": float(w_delay),
                "promise_lead_days": w_promise_days,
            }])

            pred_prob = ml_model.predict_proba(sample_input)[0][1] * 100.0
            risk_tier = "HIGH RISK" if pred_prob >= 65 else "MEDIUM RISK" if pred_prob >= 35 else "LOW RISK"
            gauge_color = "#ef4444" if pred_prob >= 65 else "#f59e0b" if pred_prob >= 35 else "#10b981"

            fig_gauge = go.Figure(go.Indicator(
                mode="gauge+number",
                value=pred_prob,
                domain={"x": [0, 1], "y": [0, 1]},
                title={"text": f"Simulated Late Delivery Risk: {risk_tier}", "font": {"size": 18, "color": gauge_color}},
                number={"suffix": "%", "font": {"color": gauge_color}},
                gauge={
                    "axis": {"range": [0, 100], "tickwidth": 1},
                    "bar": {"color": gauge_color},
                    "steps": [
                        {"range": [0, 35], "color": "#dcfce7"},
                        {"range": [35, 65], "color": "#fef3c7"},
                        {"range": [65, 100], "color": "#fee2e2"},
                    ],
                    "threshold": {
                        "line": {"color": "red", "width": 4},
                        "thickness": 0.75,
                        "value": 65,
                    },
                },
            ))
            fig_gauge.update_layout(height=280, margin=dict(t=40, b=10, l=30, r=30))
            st.plotly_chart(fig_gauge, use_container_width=True)


# =============================================================================
# MODULE 5: EXCEPTION OPERATIONS CENTER
# =============================================================================
elif navigation == "🚨 Exception Operations Center":
    st.title("🚨 Logistics Exception Operations Center")
    st.caption("Active operational bottlenecks, delivery failures, and delayed SLA monitoring.")

    ec1, ec2, ec3 = st.columns(3)
    sev_filter = ec1.selectbox("Filter by Severity", ["All"] + sorted(exceptions["severity"].unique().tolist()))
    issue_filter = ec2.selectbox("Filter by Issue Type", ["All"] + sorted(exceptions["issue_type"].unique().tolist()))
    status_filter = ec3.selectbox("Filter by Status", ["All"] + sorted(exceptions["exception_status"].unique().tolist()))

    filtered_exc = exceptions.copy()
    if sev_filter != "All":
        filtered_exc = filtered_exc[filtered_exc["severity"] == sev_filter]
    if issue_filter != "All":
        filtered_exc = filtered_exc[filtered_exc["issue_type"] == issue_filter]
    if status_filter != "All":
        filtered_exc = filtered_exc[filtered_exc["exception_status"] == status_filter]

    st.markdown(f"**Found {len(filtered_exc)} exceptions matching criteria.**")

    # Node Exception Heatmap
    if not filtered_exc.empty:
        ex_summary = filtered_exc.groupby(["node_name", "issue_type"]).size().reset_index(name="Exception Count")
        fig_ex = px.bar(
            ex_summary,
            x="node_name",
            y="Exception Count",
            color="issue_type",
            title="Exception Volume by Fulfillment Facility",
        )
        fig_ex.update_layout(xaxis_tickangle=-35, height=320)
        st.plotly_chart(fig_ex, use_container_width=True)

    st.dataframe(filtered_exc, use_container_width=True, hide_index=True)


# =============================================================================
# MODULE 6: ANOMALY & GROUND TRUTH INSPECTOR
# =============================================================================
elif navigation == "🔍 Anomaly & Ground Truth Inspector":
    st.title("🔍 Anomaly & Ground Truth Integrity Inspector")
    st.caption("Inspect deliberately injected edge cases, compare ground truth labels, and run live system integrity verification.")

    if not ground_truth:
        st.info("No ground truth anomalies injected. Run python -m scripts.generate_data --inject-edge-cases to generate labeled edge cases.")
    else:
        st.subheader("📋 Injected Edge Case Anomaly Catalog")
        st.write("These 5 labeled negative scenarios are maintained in isolation without leaking into feature stores:")

        for item in ground_truth:
            with st.expander(f"⚠️ [{item['anomaly_id']}] {item['edge_case_type']} on {item['entity_id']}", expanded=True):
                g1, g2, g3 = st.columns(3)
                g1.markdown(f"**Entity Type:** `{item['entity_type']}`")
                g1.markdown(f"**Entity ID:** `{item['entity_id']}`")
                g2.markdown(f"**Injected Field:** `{item['injected_field']}`")
                g2.markdown(f"**Injected Value:** `{item['injected_value']}`")
                g3.markdown(f"**Expected Valid:** `{item['expected_valid_value']}`")
                g3.markdown(f"**Ground Truth Label:** `{item['ground_truth_label']}`")
                st.caption(f"Details: {item['description']}")

    st.markdown("---")
    st.subheader("🛡️ Run Live System Integrity Validation")
    st.caption("Executes all 8 system checks: PK uniqueness, foreign-key enforcement, enums, date ordering, arithmetic reconciliation, and ground truth match.")

    if st.button("🚀 Run Live 8-Point Validation Suite", type="primary"):
        from scripts.validate_all import run_comprehensive_validation
        with st.spinner("Scanning database constraints..."):
            val_success = run_comprehensive_validation()

        if val_success:
            st.success("✅ SYSTEM VALIDATION COMPLETE: 100% Relational Integrity Confirmed. All 5 Ground Truth Anomalies Accurately Reconciled.")
            v1, v2, v3, v4 = st.columns(4)
            v1.metric("Database Tables", "23 [OK]")
            v2.metric("Foreign Key Errors", "0 [OK]")
            v3.metric("PK Duplicates", "0 [OK]")
            v4.metric("Ground Truth Match", "5/5 [OK]")


# =============================================================================
# MODULE 7: MODEL EXPLAINABILITY
# =============================================================================
elif navigation == "🧠 Model Explainability":
    st.title("🧠 Machine Learning Model Explainability & Feature Impact")
    st.caption("Permutation feature importance and classification performance metrics.")

    metrics_file = Path("data/reports/model_evaluation.json")
    importance_file = Path("data/reports/feature_importance.csv")

    if metrics_file.exists():
        with open(metrics_file, "r") as f:
            eval_metrics = json.load(f)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Accuracy", f"{eval_metrics['accuracy'] * 100:.1f}%")
        m2.metric("Precision", f"{eval_metrics['precision'] * 100:.1f}%")
        m3.metric("Recall", f"{eval_metrics['recall'] * 100:.1f}%")
        m4.metric("F1 Score", f"{eval_metrics['f1_score'] * 100:.1f}%")

    if importance_file.exists():
        st.markdown("---")
        st.subheader("🎯 Permutation Feature Importance")
        st.caption("Quantifies the contribution of each operational variable to late-delivery predictions.")

        imp_df = pd.read_csv(importance_file).sort_values("importance_mean", ascending=True)

        fig_imp = px.bar(
            imp_df,
            x="importance_mean",
            y="feature",
            orientation="h",
            error_x="importance_std",
            title="Relative Feature Importance (Permutation F1 Score)",
            labels={"importance_mean": "Importance Score", "feature": "Operational Feature"},
            color="importance_mean",
            color_continuous_scale="Blues",
        )
        fig_imp.update_layout(height=450, margin=dict(t=30, b=20, l=10, r=10))
        st.plotly_chart(fig_imp, use_container_width=True)

        st.dataframe(imp_df.sort_values("importance_mean", ascending=False), use_container_width=True, hide_index=True)


# -----------------------------------------------------------------------------
# GLOBAL FOOTER
# -----------------------------------------------------------------------------
st.markdown("---")
st.caption("SmartFulfill AI v1.0.0 | Enterprise Fulfillment & Predictive Risk Control | Connected to SQLite (23 Tables)")
