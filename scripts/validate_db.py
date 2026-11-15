from database.db_manager import validate_database

if __name__ == "__main__":
    result = validate_database()
    print("\nSMARTFULFILL AI DATABASE VALIDATION")
    print("-" * 45)
    print("Integrity:", result["integrity"])
    print("Foreign key errors:", result["foreign_key_errors"])
    print("\nDatabase tables:")
    for table in result["tables"]:
        print("  [OK]", table)
    print("\nTotal tables:", len(result["tables"]))
    if result["integrity"] == "ok" and result["foreign_key_errors"] == 0:
        print("\nRESULT: DATABASE VALIDATION PASSED")
    else:
        print("\nRESULT: DATABASE VALIDATION FAILED")
