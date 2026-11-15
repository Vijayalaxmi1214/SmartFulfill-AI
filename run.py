import uvicorn
from database.db_manager import initialize_database

if __name__ == "__main__":
    print("=" * 55)
    print("       SMARTFULFILL AI")
    print("  Order Fulfillment Optimization System")
    print("=" * 55)
    initialize_database()
    print("\nStarting FastAPI server...")
    print("API: http://127.0.0.1:8000")
    print("Documentation: http://127.0.0.1:8000/docs")
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)
