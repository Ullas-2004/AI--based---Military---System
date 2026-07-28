"""Import exported JSON dataset into MongoDB / AegisAI database.

Usage:
    python api/import_exported_db.py
"""
import json
import os
import sys
from datetime import datetime, timezone
from bson import ObjectId

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from config import config
from database.mongodb import get_db

EXPORT_DIR = r"C:\Users\ADMIN\Downloads\aegis_ai_db_export\aegis_ai_db_export"

FILES_AND_COLLECTIONS = [
    ("users.json", "users"),
    ("vision_detections.json", "vision_detections"),
    ("threat_predictions.json", "threat_predictions"),
    ("intelligence_reports.json", "intelligence_reports"),
    ("audit_logs.json", "audit_logs"),
]


def convert_types(doc):
    """Recursively convert strings to ObjectId and datetime objects where appropriate."""
    if isinstance(doc, dict):
        new_doc = {}
        for k, v in doc.items():
            if k == "_id" and isinstance(v, str) and len(v) == 24:
                try:
                    new_doc[k] = ObjectId(v)
                    continue
                except Exception:
                    pass
            elif isinstance(v, str) and ("_at" in k or k in ("timestamp", "detected_at")):
                try:
                    # ISO format parsing
                    dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
                    new_doc[k] = dt
                    continue
                except Exception:
                    pass
            new_doc[k] = convert_types(v)
        return new_doc
    elif isinstance(doc, list):
        return [convert_types(item) for item in doc]
    return doc


def main():
    db = get_db()
    if db is None:
        print("Error: Database connection could not be established.")
        return 1

    print(f"Importing dataset into database '{config.MONGO_DB_NAME}' from:\n  {EXPORT_DIR}\n")

    total_inserted = 0
    for filename, collection_name in FILES_AND_COLLECTIONS:
        filepath = os.path.join(EXPORT_DIR, filename)
        if not os.path.exists(filepath):
            print(f"Skipping missing file: {filename}")
            continue

        with open(filepath, "r", encoding="utf-8") as f:
            raw_docs = json.load(f)

        if not raw_docs:
            print(f"File {filename} is empty.")
            continue

        converted_docs = [convert_types(doc) for doc in raw_docs]
        coll = db[collection_name]

        # Use bulk operations or insert_many, avoiding duplicates by _id
        inserted_count = 0
        for doc in converted_docs:
            doc_id = doc.get("_id")
            if doc_id and coll.find_one({"_id": doc_id}):
                # Update existing doc
                coll.replace_one({"_id": doc_id}, doc)
            else:
                coll.insert_one(doc)
            inserted_count += 1

        print(f"Successfully processed collection '{collection_name}': {inserted_count} documents.")
        total_inserted += inserted_count

    print(f"\nImport finished. Total documents processed: {total_inserted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
