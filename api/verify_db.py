"""Standalone MongoDB connectivity and CRUD verifier.

Run before starting the app against a new database:

    python api/verify_db.py

Reads MONGO_URI / MONGO_DB_NAME from .env via config.py, so it exercises the
exact same configuration path the application uses. Never prints credentials.

Exit code 0 = everything works, 1 = something failed.
"""
import sys
import time
from datetime import datetime, timezone

from pymongo import MongoClient
from pymongo.errors import (
    OperationFailure, PyMongoError, ServerSelectionTimeoutError,
)

from config import config

PROBE_PREFIX = "_aegis_verify_"

PASS = "  [PASS]"
FAIL = "  [FAIL]"
INFO = "  [INFO]"


def redact(uri: str) -> str:
    """Strip credentials so the URI can be logged safely."""
    if "@" not in uri:
        return uri
    scheme, _, rest = uri.partition("://")
    _, _, host = rest.partition("@")
    return f"{scheme}://<credentials-hidden>@{host}"


def preflight(uri: str) -> list:
    """Catch common URI mistakes before we waste a connection timeout on them."""
    problems = []
    if "<db_password>" in uri or "<password>" in uri:
        problems.append(
            "MONGO_URI still contains the literal <db_password> placeholder. "
            "Replace it with the real Atlas database-user password in .env."
        )
    if uri.startswith("mongodb+srv://"):
        # An SRV URI must not carry a port; Atlas resolves it via DNS.
        host = uri.split("@")[-1].split("/")[0]
        if ":" in host:
            problems.append("mongodb+srv:// URIs must not include a port number.")
    if uri.startswith("mongodb") and "@" in uri:
        credentials = uri.split("://", 1)[1].split("@")[0]
        if ":" in credentials:
            password = credentials.split(":", 1)[1]
            # Unencoded reserved characters silently corrupt the parsed URI.
            for ch in "@/?#[]":
                if ch in password:
                    problems.append(
                        f"The password contains an unencoded '{ch}'. "
                        "Percent-encode it (see the note in .env)."
                    )
                    break
    return problems


def main() -> int:
    failures = []
    print("AegisAI database verification")
    print("=" * 60)
    print(f"{INFO} URI      : {redact(config.MONGO_URI)}")
    print(f"{INFO} Database : {config.MONGO_DB_NAME}")
    print(f"{INFO} Timeout  : {config.MONGO_TIMEOUT_MS} ms")
    print("-" * 60)

    blockers = preflight(config.MONGO_URI)
    if blockers:
        for problem in blockers:
            print(f"{FAIL} {problem}")
        return 1

    # --- 1. Connect -------------------------------------------------------
    started = time.monotonic()
    try:
        client = MongoClient(
            config.MONGO_URI,
            serverSelectionTimeoutMS=config.MONGO_TIMEOUT_MS,
            tz_aware=True,
        )
        client.admin.command("ping")
        latency_ms = (time.monotonic() - started) * 1000
        print(f"{PASS} Connected ({latency_ms:.0f} ms)")
    except ServerSelectionTimeoutError as exc:
        print(f"{FAIL} Could not reach the server.")
        print(f"         {str(exc)[:200]}")
        print("\n  Common causes:")
        print("   - Your IP is not in the Atlas Network Access allowlist")
        print("   - Wrong cluster hostname in MONGO_URI")
        print("   - Firewall blocking outbound TCP 27017 / SRV DNS lookups")
        return 1
    except PyMongoError as exc:
        print(f"{FAIL} Connection error: {type(exc).__name__}: {str(exc)[:200]}")
        return 1

    # --- 2. Server info ---------------------------------------------------
    try:
        info = client.server_info()
        print(f"{PASS} Server version {info.get('version', 'unknown')}")
        topology = client.topology_description.topology_type_name
        print(f"{INFO} Topology: {topology}")
    except OperationFailure as exc:
        # Atlas free tiers restrict some admin commands; not fatal.
        print(f"{INFO} Server info unavailable (restricted): {exc.code_name}")

    db = client[config.MONGO_DB_NAME]

    # --- 3. Authentication / authorisation --------------------------------
    try:
        db.list_collection_names()
        print(f"{PASS} Authenticated and authorised to read the database")
    except OperationFailure as exc:
        print(f"{FAIL} Auth/permission problem: {exc.code_name} - {exc.details.get('errmsg', '')[:150]}")
        print("\n  The database user likely lacks readWrite on this database.")
        return 1

    # --- 4. CRUD round trip on a throwaway collection ---------------------
    probe = db[f"{PROBE_PREFIX}probe"]
    try:
        probe.drop()

        # CREATE
        doc = {"marker": "aegis-verify", "created_at": datetime.now(timezone.utc), "n": 1}
        inserted_id = probe.insert_one(doc).inserted_id
        print(f"{PASS} CREATE  insert_one -> {inserted_id}")

        # READ
        found = probe.find_one({"_id": inserted_id})
        assert found and found["marker"] == "aegis-verify", "round-tripped document mismatch"
        print(f"{PASS} READ    find_one returned the document")

        # Verify tz-aware datetimes survive the round trip; the app relies on
        # comparing stored created_at against timezone-aware "now".
        if found["created_at"].tzinfo is None:
            failures.append("datetimes came back naive (tz_aware not applied)")
            print(f"{FAIL} READ    datetime lost its timezone")
        else:
            print(f"{PASS} READ    datetime is timezone-aware")

        # UPDATE
        probe.update_one({"_id": inserted_id}, {"$set": {"n": 2}})
        assert probe.find_one({"_id": inserted_id})["n"] == 2
        print(f"{PASS} UPDATE  update_one applied")

        # Sort + limit: the access pattern every history view uses.
        probe.insert_many([
            {"marker": "aegis-verify", "created_at": datetime.now(timezone.utc), "n": i}
            for i in range(3, 8)
        ])
        recent = list(probe.find().sort("created_at", -1).limit(3))
        assert len(recent) == 3
        print(f"{PASS} QUERY   sort + skip + limit returned {len(recent)} docs")

        # Aggregation, used by /api/data/analytics.
        agg = list(probe.aggregate([{"$group": {"_id": None, "total": {"$sum": "$n"}}}]))
        print(f"{PASS} QUERY   aggregation pipeline ran (sum={agg[0]['total']})")

        # Index creation, incl. the unique constraint login depends on.
        probe.create_index("marker", name="probe_marker")
        probe.create_index("n", unique=True, name="probe_unique_n")
        print(f"{PASS} INDEX   created standard and unique indexes")

        # The unique index must actually reject a duplicate; auth_routes relies
        # on DuplicateKeyError rather than a find-then-insert race.
        from pymongo.errors import DuplicateKeyError
        try:
            probe.insert_one({"n": 2})
            failures.append("unique index did not reject a duplicate")
            print(f"{FAIL} INDEX   duplicate was NOT rejected")
        except DuplicateKeyError:
            print(f"{PASS} INDEX   duplicate correctly rejected")

        # DELETE
        deleted = probe.delete_many({"marker": "aegis-verify"}).deleted_count
        print(f"{PASS} DELETE  delete_many removed {deleted} docs")

    except AssertionError as exc:
        failures.append(f"CRUD assertion failed: {exc}")
        print(f"{FAIL} CRUD assertion failed: {exc}")
    except OperationFailure as exc:
        failures.append(f"CRUD operation failed: {exc.code_name}")
        print(f"{FAIL} CRUD failed: {exc.code_name} - {exc.details.get('errmsg', '')[:150]}")
        print("         The user probably has read-only access.")
    except PyMongoError as exc:
        failures.append(f"CRUD error: {type(exc).__name__}")
        print(f"{FAIL} CRUD error: {type(exc).__name__}: {str(exc)[:150]}")
    finally:
        try:
            probe.drop()
            print(f"{INFO} Probe collection dropped")
        except PyMongoError:
            print(f"{INFO} Could not drop probe collection (harmless leftover)")

    # --- 5. Application collections ---------------------------------------
    print("-" * 60)
    expected = [
        "users", "vision_detections", "threat_predictions",
        "intelligence_reports", "audit_logs",
    ]
    try:
        existing = set(db.list_collection_names())
        for name in expected:
            count = db[name].estimated_document_count() if name in existing else 0
            state = "exists" if name in existing else "not created yet"
            print(f"{INFO} {name:<22} {state:<16} ({count} docs)")
    except PyMongoError as exc:
        print(f"{INFO} Could not enumerate collections: {type(exc).__name__}")

    client.close()
    print("=" * 60)
    if failures:
        print(f"RESULT: FAILED ({len(failures)} issue(s))")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("RESULT: All database operations verified successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
