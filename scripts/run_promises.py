
from database.stage4_db import initialize_stage4_database
from generators.delivery_promise_engine import calculate_delivery_promises


def main():
    print("=" * 55)
    print("SMARTFULFILL AI - DELIVERY PROMISE ENGINE")
    print("=" * 55)

    initialize_stage4_database()

    print("\nCalculating delivery promises...")
    calculate_delivery_promises()

    print("\nSTAGE 4 EXECUTION COMPLETED")


if __name__ == "__main__":
    main()
