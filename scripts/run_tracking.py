
from database.stage5_db import initialize_stage5_database
from generators.tracking_engine import run_tracking_simulation


def main():
    print("=" * 55)
    print("SMARTFULFILL AI - SHIPMENT TRACKING")
    print("=" * 55)

    initialize_stage5_database()
    run_tracking_simulation()

    print("\nSTAGE 5 EXECUTION COMPLETED")


if __name__ == "__main__":
    main()
