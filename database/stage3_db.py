
from database.db_manager import get_connection
from config.settings import BASE_DIR


def initialize_stage3_database():
    schema_path = BASE_DIR / "database" / "stage3_schema.sql"

    if not schema_path.exists():
        raise FileNotFoundError(schema_path)

    connection = get_connection()

    try:
        schema = schema_path.read_text(encoding="utf-8")
        connection.executescript(schema)
        connection.commit()

        print("Stage 3 database tables initialized.")

    finally:
        connection.close()
