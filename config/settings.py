from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "data"
GENERATED_DIR = DATA_DIR / "generated"
EXPORT_DIR = DATA_DIR / "exports"
GROUND_TRUTH_DIR = DATA_DIR / "ground_truth"

DATABASE_PATH = DATA_DIR / "smartfulfill.db"
SCHEMA_PATH = BASE_DIR / "database" / "schema.sql"

RANDOM_SEED = 20261022
STARTER_ORDERS = 100
FULL_ORDERS = 50000
TOTAL_NODES = 20
TOTAL_CARRIERS = 10
TOTAL_TRACKING_EVENTS = 100000

def create_directories():
    for directory in (DATA_DIR, GENERATED_DIR, EXPORT_DIR, GROUND_TRUTH_DIR):
        directory.mkdir(parents=True, exist_ok=True)
