"""Seed a realistic multi-sector operational scenario into the database.

    python api/seed_demo_data.py           # add scenario data
    python api/seed_demo_data.py --reset   # wipe app data first

Generates 7 days of correlated activity across four sectors so the dashboard,
analytics, forecast and reports all have believable data to render. Every
prediction is produced by the real scoring model, not fabricated, so the stored
scores are internally consistent with the telemetry beside them.
"""
import argparse
import os
import random
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from config import config  # noqa: E402
from database.mongodb import get_db  # noqa: E402
from middleware.auth import hash_password  # noqa: E402
from services.ml_service import predict_threat_score  # noqa: E402

RANDOM_SEED = 7
random.seed(RANDOM_SEED)

# --- Operational picture -----------------------------------------------------
# Four sectors with distinct signatures, so analytics show real differentiation
# rather than uniform noise.
SECTORS = [
    # name,        terrain,     lat,     lng,    pressure (0-1), typical assets
    ("Sector Alpha",   "Desert",   34.052, 72.344, 0.85, ["Tank", "Truck", "Soldier"]),
    ("Sector Bravo",   "Mountain", 34.120, 72.410, 0.60, ["UAV", "Helicopter", "Soldier"]),
    ("Sector Charlie", "Forest",   33.980, 72.500, 0.35, ["Soldier", "Truck", "Civilian Car"]),
    ("Sector Delta",   "Urban",    34.080, 72.380, 0.50, ["Civilian Car", "Truck", "Soldier"]),
]

WEATHER_BY_HOUR = {
    (0, 6):   ["Fog", "Fog", "Overcast", "Clear"],
    (6, 12):  ["Clear", "Clear", "Overcast", "Rain"],
    (12, 18): ["Clear", "Overcast", "Rain", "Clear"],
    (18, 24): ["Overcast", "Fog", "Clear", "Snow"],
}

DEMO_USERS = [
    ("cmdr.hayes",    "Falcon#Ridge77", "commander"),
    ("analyst.rao",   "Kestrel$Vale21", "analyst"),
    ("analyst.okafor", "Sable&Creek09", "analyst"),
    ("sysadmin.chen", "Onyx!Harbor44",  "admin"),
]

SOURCE_FILES = [
    "uav_feed_alpha_0412.jpg", "tower_cam_bravo_night.png",
    "drone_sweep_charlie.jpg", "checkpoint_delta_gate.jpg",
    "thermal_bravo_ridge.png", "patrol_alpha_convoy.jpg",
]

COCO_FOR = {
    "Tank": "truck", "Truck": "truck", "Soldier": "person",
    "UAV": "airplane", "Helicopter": "airplane", "Civilian Car": "car",
}


def time_of_day(hour: int) -> str:
    if hour < 6:
        return "Night"
    if hour < 12:
        return "Morning"
    if hour < 18:
        return "Afternoon"
    return "Evening"


def weather_for(hour: int) -> str:
    for (lo, hi), options in WEATHER_BY_HOUR.items():
        if lo <= hour < hi:
            return random.choice(options)
    return "Clear"


def jitter(value: float, spread: float) -> float:
    return round(value + random.uniform(-spread, spread), 4)


def seed_users(db) -> dict:
    created = {}
    for username, password, role in DEMO_USERS:
        if db.users.find_one({"username_lower": username.lower()}):
            print(f"  user exists, skipping: {username}")
            continue
        result = db.users.insert_one({
            "username": username,
            "username_lower": username.lower(),
            "password": hash_password(password),
            "role": role,
            "status": "active",
            "created_at": datetime.now(timezone.utc) - timedelta(days=random.randint(30, 200)),
        })
        created[username] = str(result.inserted_id)
        print(f"  + {role:<10} {username}")
    return created


def seed_activity(db, days: int = 7) -> None:
    now = datetime.now(timezone.utc)
    predictions, detections, audit = [], [], []

    for day_offset in range(days, 0, -1):
        # Activity ramps toward the present, so trends are visible.
        intensity = 1.0 + (days - day_offset) * 0.12
        events_today = int(random.randint(4, 9) * intensity)

        for _ in range(events_today):
            sector, terrain, lat, lng, pressure, assets = random.choice(SECTORS)
            hour = random.choices(
                range(24),
                weights=[3 if h < 6 or h >= 20 else 1 for h in range(24)],  # night-heavy
            )[0]
            when = now - timedelta(days=day_offset, hours=random.randint(0, 23) - hour % 1,
                                   minutes=random.randint(0, 59))
            when = when.replace(hour=hour)

            obj = random.choice(assets)
            weather = weather_for(hour)
            tod = time_of_day(hour)
            # Higher-pressure sectors see contacts closer to the border.
            distance = round(max(0.2, random.expovariate(1 / (18 * (1 - pressure * 0.7)))), 2)
            distance = min(distance, 49.0)
            confidence = round(random.uniform(62, 98.5), 2)

            # Real model call: stored scores stay consistent with their inputs.
            ml = predict_threat_score(obj, confidence, weather, terrain, tod, distance)

            predictions.append({
                "telemetry": {
                    "object": obj, "confidence": confidence, "weather": weather,
                    "terrain": terrain, "time_of_day": tod, "distance_km": distance,
                },
                "ml_output": ml,
                "location": {"lat": jitter(lat, 0.05), "lng": jitter(lng, 0.05),
                             "sector": sector},
                "scored_by": "seed",
                "created_at": when,
            })

            # Roughly a third of contacts also have imagery attached.
            if random.random() < 0.35:
                count = random.randint(1, 4)
                dets = []
                for _ in range(count):
                    d_obj = random.choice(assets)
                    dets.append({
                        "object": d_obj,
                        "source_class": COCO_FOR[d_obj],
                        "is_proxy_class": True,
                        "confidence": round(random.uniform(55, 96), 2),
                        "bbox": {"x1": jitter(120, 100), "y1": jitter(160, 90),
                                 "x2": jitter(480, 120), "y2": jitter(520, 100)},
                        "detected_at": when,
                    })
                dets.sort(key=lambda d: d["confidence"], reverse=True)
                detections.append({
                    "original_filename": random.choice(SOURCE_FILES),
                    "detections": dets,
                    "unmapped_detections": (
                        [{"source_class": "bird", "confidence": round(random.uniform(45, 70), 2)}]
                        if random.random() < 0.2 else []
                    ),
                    "total_objects": len(dets),
                    "model": "yolov8n (COCO proxy classes)",
                    "uploaded_by": "seed",
                    "created_at": when,
                    "status": random.choice(
                        ["pending_analyst_review", "pending_analyst_review", "confirmed"]
                    ),
                })

            if random.random() < 0.25:
                audit.append({
                    "user_id": "seed",
                    "action": random.choice(
                        ["LOGIN_SUCCESS", "VISION_DETECT", "ASSISTANT_QUERY", "LOGIN_FAILED"]
                    ),
                    "details": f"{sector} activity",
                    "ip_address": f"10.20.{random.randint(1,40)}.{random.randint(2,250)}",
                    "timestamp": when,
                })

    if predictions:
        db.threat_predictions.insert_many(predictions)
    if detections:
        db.vision_detections.insert_many(detections)
    if audit:
        db.audit_logs.insert_many(audit)

    print(f"  + {len(predictions)} threat predictions")
    print(f"  + {len(detections)} vision detections")
    print(f"  + {len(audit)} audit events")

    levels = {}
    for p in predictions:
        levels[p["ml_output"]["threat_level"]] = levels.get(p["ml_output"]["threat_level"], 0) + 1
    print(f"  threat distribution: {levels}")


def reset(db) -> None:
    for name in ["users", "vision_detections", "threat_predictions",
                 "intelligence_reports", "audit_logs"]:
        deleted = db[name].delete_many({}).deleted_count
        print(f"  cleared {name} ({deleted} docs)")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="wipe app data first")
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()

    db = get_db()
    if db is None:
        print("Database unreachable. Check MONGO_URI in .env.")
        return 1

    print(f"Seeding '{config.MONGO_DB_NAME}'")
    print("-" * 55)
    if args.reset:
        print("Resetting collections:")
        reset(db)
        print()

    print("Users:")
    seed_users(db)
    print("\nActivity:")
    seed_activity(db, args.days)

    print("-" * 55)
    for name in ["users", "vision_detections", "threat_predictions", "audit_logs"]:
        print(f"  {name:<22}{db[name].count_documents({}):>5} docs")
    print("\nDemo credentials:")
    for username, password, role in DEMO_USERS:
        print(f"  {role:<10} {username:<16} {password}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
