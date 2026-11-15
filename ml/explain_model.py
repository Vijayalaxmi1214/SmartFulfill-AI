
from pathlib import Path
import json

import joblib
import pandas as pd

from sklearn.inspection import permutation_importance
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    classification_report,
    confusion_matrix,
)


# Project paths
ROOT = Path(__file__).resolve().parent.parent

DATA_FILE = ROOT / "data" / "processed" / "late_delivery_training.csv"
MODEL_FILE = ROOT / "models" / "late_delivery_model.joblib"
OUTPUT_DIR = ROOT / "data" / "reports"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def main():

    print("\nSMARTFULFILL AI - MODEL EXPLAINABILITY")
    print("=" * 55)

    if not DATA_FILE.exists():
        raise FileNotFoundError(DATA_FILE)

    if not MODEL_FILE.exists():
        raise FileNotFoundError(MODEL_FILE)

    # Load data and trained model
    data = pd.read_csv(DATA_FILE)
    model = joblib.load(MODEL_FILE)

    target = "is_late"

    X = data.drop(columns=[target])
    y = data[target].astype(int)

    # Reproduce the original train/test split
    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.25,
        random_state=42,
        stratify=y,
    )

    # Evaluate model on test data
    predictions = model.predict(X_test)

    accuracy = accuracy_score(y_test, predictions)
    precision = precision_score(
        y_test, predictions, zero_division=0
    )
    recall = recall_score(
        y_test, predictions, zero_division=0
    )
    f1 = f1_score(
        y_test, predictions, zero_division=0
    )

    print("\nMODEL PERFORMANCE")
    print("-" * 55)

    print(f"Accuracy : {accuracy:.4f}")
    print(f"Precision: {precision:.4f}")
    print(f"Recall   : {recall:.4f}")
    print(f"F1 Score : {f1:.4f}")

    print("\nCONFUSION MATRIX")
    print(confusion_matrix(y_test, predictions))

    print("\nCLASSIFICATION REPORT")
    print(classification_report(
        y_test,
        predictions,
        zero_division=0,
    ))

    # Explain predictions using permutation importance
    print("\nCALCULATING FEATURE IMPORTANCE...")

    result = permutation_importance(
        model,
        X_test,
        y_test,
        n_repeats=20,
        random_state=42,
        scoring="f1",
        n_jobs=-1,
    )

    importance = pd.DataFrame({
        "feature": X.columns,
        "importance_mean": result.importances_mean,
        "importance_std": result.importances_std,
    })

    importance = importance.sort_values(
        "importance_mean",
        ascending=False,
    )

    output_file = OUTPUT_DIR / "feature_importance.csv"

    importance.to_csv(output_file, index=False)

    print("\nTOP IMPORTANT FEATURES")
    print("-" * 55)

    print(importance.head(10).to_string(index=False))

    print(f"\nFeature report saved: {output_file}")

    # Save evaluation results
    metrics = {
        "accuracy": round(float(accuracy), 4),
        "precision": round(float(precision), 4),
        "recall": round(float(recall), 4),
        "f1_score": round(float(f1), 4),
        "test_records": int(len(X_test)),
        "training_records": int(len(X_train)),
    }

    metrics_file = OUTPUT_DIR / "model_evaluation.json"

    with open(metrics_file, "w") as file:
        json.dump(metrics, file, indent=4)

    print(f"Evaluation saved: {metrics_file}")

    print("\nMODEL EXPLAINABILITY COMPLETED")


if __name__ == "__main__":
    main()
