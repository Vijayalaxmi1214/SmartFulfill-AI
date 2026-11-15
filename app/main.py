from datetime import datetime, timezone
from fastapi import FastAPI

from database.db_manager import initialize_database, validate_database

app = FastAPI(
    title="SmartFulfill AI",
    description="Intelligent Order Fulfillment and Delivery Promise Optimization System",
    version="1.0.0",
)

@app.on_event("startup")
def startup_event():
    initialize_database()

@app.get("/")
def home():
    return {
        "project": "SmartFulfill AI",
        "message": "Fulfillment optimization system is running",
        "status": "ACTIVE",
    }

@app.get("/health")
def health():
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

@app.get("/database/status")
def database_status():
    result = validate_database()
    return {
        "database": "smartfulfill.db",
        "integrity": result["integrity"],
        "foreign_key_errors": result["foreign_key_errors"],
        "total_tables": len(result["tables"]),
        "tables": result["tables"],
    }
