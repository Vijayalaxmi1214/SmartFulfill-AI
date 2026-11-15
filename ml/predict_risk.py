
from pathlib import Path

import joblib
import pandas as pd

from database.db_manager import get_connection


MODEL_FILE = Path("models/late_delivery_model.joblib")
OUTPUT_DIR = Path("data/reports")
OUTPUT_FILE = OUTPUT_DIR / "shipment_risk_predictions.csv"


def get_active_shipments():

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
            dp.promised_delivery_date
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
        WHERE s.shipment_status = 'IN_TRANSIT'
          AND s.dispatched_at IS NOT NULL
    """

    try:
        return pd.read_sql_query(query, connection)
    finally:
        connection.close()


def prepare_features(df):

    df = df.copy()

    date_columns = [
        "order_created_at",
        "created_at",
        "dispatched_at",
        "promised_delivery_date",
    ]

    for column in date_columns:
        df[column] = pd.to_datetime(
            df[column],
            errors="coerce",
        )

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

    return df[feature_columns]


def run_risk_predictions():

    if not MODEL_FILE.exists():
        raise FileNotFoundError(
            "Trained model not found. Run "
            "python -m ml.train_model first."
        )

    model = joblib.load(MODEL_FILE)

    shipments = get_active_shipments()

    print("\nSMARTFULFILL AI - DELIVERY RISK PREDICTION")
    print("------------------------------------------")
    print("Active shipments found:", len(shipments))

    if shipments.empty:
        print("No in-transit shipments available.")
        return pd.DataFrame()

    features = prepare_features(shipments)

    probabilities = model.predict_proba(features)

    late_class_index = list(model.classes_).index(1)

    late_probabilities = probabilities[:, late_class_index]

    results = shipments[
        ["shipment_id", "order_id", "carrier_id", "node_id",
         "promised_delivery_date"]
    ].copy()

    results["late_risk_probability"] = (
        late_probabilities.round(4)
    )

    results["late_risk_percentage"] = (
        results["late_risk_probability"] * 100
    ).round(2)

    def classify_risk(probability):
        if probability >= 0.65:
            return "HIGH"
        elif probability >= 0.35:
            return "MEDIUM"
        return "LOW"

    results["risk_level"] = (
        results["late_risk_probability"].apply(classify_risk)
    )

    results = results.sort_values(
        "late_risk_probability",
        ascending=False,
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    results.to_csv(OUTPUT_FILE, index=False)

    print("\nPREDICTION SUMMARY")
    print("------------------")
    print("High risk:", int((results["risk_level"] == "HIGH").sum()))
    print("Medium risk:", int((results["risk_level"] == "MEDIUM").sum()))
    print("Low risk:", int((results["risk_level"] == "LOW").sum()))

    print("\nSHIPMENT RISK DETAILS")
    print("---------------------")

    for _, row in results.iterrows():
        print(
            "{} | {} | {}%".format(
                row["shipment_id"],
                row["risk_level"],
                row["late_risk_percentage"],
            )
        )

    print("\nSaved predictions:", OUTPUT_FILE)
    print("DELIVERY RISK PREDICTION COMPLETED")

    return results


if __name__ == "__main__":
    run_risk_predictions()
