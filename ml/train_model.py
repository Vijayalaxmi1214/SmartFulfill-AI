
from pathlib import Path
import json

import joblib
import pandas as pd

from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


DATA_FILE = Path("data/processed/late_delivery_training.csv")
MODEL_DIR = Path("models")
MODEL_FILE = MODEL_DIR / "late_delivery_model.joblib"
METRICS_FILE = MODEL_DIR / "model_metrics.json"


CATEGORICAL_FEATURES = [
    "carrier_id",
    "node_id",
    "service_level_id",
    "destination_zone_id",
    "requested_service_level_id",
    "node_type",
]

NUMERIC_FEATURES = [
    "priority",
    "transit_business_days",
    "order_created_weekday",
    "order_created_hour",
    "dispatch_delay_hours",
    "promise_lead_days",
]

TARGET = "is_late"


def train_model():

    if not DATA_FILE.exists():
        raise FileNotFoundError(
            "Training dataset not found. Run "
            "python -m ml.prepare_training_data first."
        )

    df = pd.read_csv(DATA_FILE)

    if len(df) < 20:
        raise ValueError(
            "Not enough records for a reliable train/test split."
        )

    if df[TARGET].nunique() < 2:
        raise ValueError(
            "Training data must contain both on-time and late shipments."
        )

    feature_columns = (
        CATEGORICAL_FEATURES + NUMERIC_FEATURES
    )

    X = df[feature_columns].copy()
    y = df[TARGET].astype(int)

    # Keep enough examples of both classes in training and testing.
    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.25,
        random_state=42,
        stratify=y,
    )

    categorical_pipeline = Pipeline(
        steps=[
            (
                "imputer",
                SimpleImputer(strategy="most_frequent"),
            ),
            (
                "encoder",
                OneHotEncoder(handle_unknown="ignore"),
            ),
        ]
    )

    numeric_pipeline = Pipeline(
        steps=[
            (
                "imputer",
                SimpleImputer(strategy="median"),
            ),
            (
                "scaler",
                StandardScaler(),
            ),
        ]
    )

    preprocessor = ColumnTransformer(
        transformers=[
            (
                "categorical",
                categorical_pipeline,
                CATEGORICAL_FEATURES,
            ),
            (
                "numeric",
                numeric_pipeline,
                NUMERIC_FEATURES,
            ),
        ]
    )

    classifier = RandomForestClassifier(
        n_estimators=300,
        max_depth=8,
        min_samples_split=4,
        class_weight="balanced",
        random_state=42,
    )

    model = Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            ("classifier", classifier),
        ]
    )

    print("\nTRAINING RANDOM FOREST MODEL...")
    model.fit(X_train, y_train)

    predictions = model.predict(X_test)

    accuracy = accuracy_score(y_test, predictions)
    precision = precision_score(
        y_test,
        predictions,
        zero_division=0,
    )
    recall = recall_score(
        y_test,
        predictions,
        zero_division=0,
    )
    f1 = f1_score(
        y_test,
        predictions,
        zero_division=0,
    )

    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    joblib.dump(model, MODEL_FILE)

    metrics = {
        "model_name": "Random Forest Classifier",
        "training_records": int(len(X_train)),
        "testing_records": int(len(X_test)),
        "total_records": int(len(df)),
        "on_time_records": int((y == 0).sum()),
        "late_records": int((y == 1).sum()),
        "accuracy": round(float(accuracy), 4),
        "precision": round(float(precision), 4),
        "recall": round(float(recall), 4),
        "f1_score": round(float(f1), 4),
        "confusion_matrix": confusion_matrix(
            y_test,
            predictions,
            labels=[0, 1],
        ).tolist(),
    }

    with open(METRICS_FILE, "w", encoding="utf-8") as file:
        json.dump(metrics, file, indent=4)

    print("\nSTAGE 8 - MODEL EVALUATION")
    print("-----------------------------------")
    print("Model:", metrics["model_name"])
    print("Training records:", metrics["training_records"])
    print("Testing records:", metrics["testing_records"])
    print("Accuracy:", metrics["accuracy"])
    print("Precision:", metrics["precision"])
    print("Recall:", metrics["recall"])
    print("F1 Score:", metrics["f1_score"])

    print("\nCONFUSION MATRIX")
    print(
        confusion_matrix(
            y_test,
            predictions,
            labels=[0, 1],
        )
    )

    print("\nCLASSIFICATION REPORT")
    print(
        classification_report(
            y_test,
            predictions,
            labels=[0, 1],
            target_names=["On-time", "Late"],
            zero_division=0,
        )
    )

    print("Saved model:", MODEL_FILE)
    print("Saved metrics:", METRICS_FILE)
    print("\nSTAGE 8 MODEL TRAINING COMPLETED")

    return model, metrics


if __name__ == "__main__":
    train_model()
