
from config.settings import BASE_DIR
from database.db_manager import get_connection


def initialize_stage5_database():
    schema_path = BASE_DIR / "database" / "stage5_schema.sql"

    if not schema_path.exists():
        raise FileNotFoundError(
            "Stage 5 schema not found: {}".format(schema_path)
        )

    connection = get_connection()

    try:
        schema = schema_path.read_text(encoding="utf-8")
        connection.executescript(schema)
        connection.commit()
        print("Stage 5 database initialized successfully.")

    finally:
        connection.close()
