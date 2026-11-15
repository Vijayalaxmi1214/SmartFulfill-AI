import argparse

from database.db_manager import validate_database
from generators.allocation_engine import allocate_orders
from generators.delivery_promise_engine import calculate_delivery_promises
from generators.edge_case_injector import inject_edge_cases
from generators.export_data import export_all_tables
from generators.master_generator import generate_master_data
from generators.order_generator import generate_orders
from generators.tracking_engine import run_tracking_simulation


def main():
    parser = argparse.ArgumentParser(
        description="SmartFulfill AI Synthetic Data Generator"
    )

    parser.add_argument(
        "--orders",
        type=int,
        default=100,
        help="Number of synthetic orders to generate (e.g. 100 for starter, 50000 for full baseline)",
    )

    parser.add_argument(
        "--inject-edge-cases",
        action="store_true",
        help="Inject the 5 labeled edge cases and output ground truth catalog",
    )

    args = parser.parse_args()

    if args.orders < 1 or args.orders > 50000:
        parser.error("Orders must be between 1 and 50000.")

    print("=" * 60)
    print("       SMARTFULFILL AI SYNTHETIC DATA GENERATOR")
    print("=" * 60)
    print(f"Target orders: {args.orders} | Inject edge cases: {args.inject_edge_cases}")

    print("\n[Step 1/5] Generating master data...")
    generate_master_data()

    print("\n[Step 2/5] Generating customer orders and lines...")
    generate_orders(args.orders)

    print("\n[Step 3/5] Allocating orders across fulfillment nodes...")
    allocate_orders()

    print("\n[Step 4/5] Calculating delivery promises and SLA targets...")
    calculate_delivery_promises()

    print("\n[Step 5/5] Simulating shipment transit tracking events...")
    run_tracking_simulation()

    if args.inject_edge_cases:
        print("\n[Bonus Step] Injecting 5 labeled negative edge cases...")
        inject_edge_cases()

    print("\nExporting CSV files...")
    export_all_tables()

    print("\nValidating database...")
    result = validate_database()
    print("Integrity:", result["integrity"])
    print("Foreign key errors:", result["foreign_key_errors"])
    print("Total database tables:", len(result["tables"]))

    if result["integrity"] == "ok" and result["foreign_key_errors"] == 0:
        print("\nSMARTFULFILL DATA GENERATION SUCCESSFUL")
    else:
        raise RuntimeError("Database validation failed.")


if __name__ == "__main__":
    main()
