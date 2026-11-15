
from pathlib import Path

import pandas as pd

from database.db_manager import get_connection


OUTPUT_DIR = Path("data") / "processed"
OUTPUT_FILE = OUTPUT_DIR / "late_delivery_training.csv"


def prepare_training_data():
    """Build a leakage-safe training dataset from delivered shipments."""

    connection = get_connection()

    query = """
        SELECT
            s.shipment_id,
            s.order_id,
            s.node_id,
            s.carrier_id,
            s.service_level_id,
            s.created_at,
            s.dispatched_at,
            o.order_created_at,
            o.destination_zone_id,
            o.requested_service_level_id,
            fn.node_type,
            sl.transit_business_days,
            sl.priority,
            dp.promised_delivery_date,
            s.delivered_at
        FROM shipments s
        JOIN orders o
            ON o.order_id = s.order_id
        JOIN fulfillment_nodes fn
            ON fn.node_id = s.node_id
        JOIN service_levels sl
            ON sl.service_level_id = s.service_level_id
        JOIN (
            SELECT
                order_id,
                MAX(promise_version) AS latest_version
            FROM delivery_promises
            GROUP BY order_id
        ) latest
            ON latest.order_id = s.order_id
        JOIN delivery_promises dp
            ON dp.order_id = latest.order_id
            AND dp.promise_version = latest.latest_version
        WHERE s.shipment_status = 'DELIVERED'
          AND s.delivered_at IS NOT NULL
          AND s.dispatched_at IS NOT NULL
    """

    try:
        df = pd.read_sql_query(query, connection)
    finally:
        connection.close()

    if df.empty:
        raise ValueError("No delivered shipments found for training.")

    # Convert dates safely.
    date_columns = [
        "order_created_at",
        "created_at",
        "dispatched_at",
        "promised_delivery_date",
        "delivered_at",
    ]

    for column in date_columns:
        df[column] = pd.to_datetime(
            df[column],
            errors="coerce",
        )

    df = df.dropna(
        subset=[
            "order_created_at",
            "dispatched_at",
            "promised_delivery_date",
            "delivered_at",
        ]
    ).copy()

    # Target label: 1 means delivered late, 0 means on time.
    df["is_late"] = (
        df["delivered_at"].dt.date
        > df["promised_delivery_date"].dt.date
    ).astype(int)

    # Features available at dispatch time.
    df["order_created_weekday"] = (
        df["order_created_at"].dt.weekday
    )

    df["order_created_hour"] = (
        df["order_created_at"].dt.hour
    )

    df["dispatch_delay_hours"] = (
        (df["dispatched_at"] - df["created_at"])
        .dt.total_seconds() / 3600
    )

    df["promise_lead_days"] = (
        df["promised_delivery_date"].dt.normalize()
        - df["order_created_at"].dt.normalize()
    ).dt.days

    feature_columns = [
        "carrier_id",
        "node_id",
        "service_level_id",
        "destination_zone_id",
        "requested_service_level_id",
        "node_type",
        "priority",
        "transit_business_days",
        "order_created_weekday",
        "order_created_hour",
        "dispatch_delay_hours",
        "promise_lead_days",
    ]

    # Keep only model features and the target.
    training_data = df[feature_columns + ["is_late"]].copy()

    training_data = training_data.replace(
        [float("inf"), float("-inf")],
        pd.NA,
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    training_data.to_csv(OUTPUT_FILE, index=False)

    print("\nSTAGE 8 - TRAINING DATA PREPARATION")
    print("-----------------------------------")
    print("Delivered shipments available:", len(training_data))
    print("On-time shipments:", int((training_data["is_late"] == 0).sum()))
    print("Late shipments:", int((training_data["is_late"] == 1).sum()))
    print("Features:", len(feature_columns))
    print("Saved to:", OUTPUT_FILE)
    print("\nTraining dataset prepared successfully.")

    return training_data


if __name__ == "__main__":
    prepare_training_data()
