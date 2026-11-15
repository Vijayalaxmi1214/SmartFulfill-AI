
from database.db_manager import get_connection
from config.settings import BASE_DIR


def initialize_stage4_database():
    schema_path = BASE_DIR / "database" / "stage4_schema.sql"

    if not schema_path.exists():
        raise FileNotFoundError(schema_path)

    connection = get_connection()

    try:
        schema = schema_path.read_text(encoding="utf-8")
        connection.executescript(schema)
        connection.commit()
        print("Stage 4 database initialized successfully.")

    finally:
        connection.close()
