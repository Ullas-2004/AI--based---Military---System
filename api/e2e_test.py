"""End-to-end test suite against a running AegisAI stack.

    python api/e2e_test.py                       # test http://127.0.0.1:5332
    python api/e2e_test.py --base http://host:port

Unlike the pytest suite (which uses an in-memory database), this drives the real
HTTP surface against the real Atlas database, so it exercises the network stack,
serialization, auth middleware and persistence together.

Exit code 0 = all passed.
"""
import argparse
import io
import json
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import requests

BASE = "http://127.0.0.1:5332"
TIMEOUT = 60

PASSED, FAILED = [], []
_section = ""

# A 1x1 PNG - smallest valid image for upload-path tests.
TINY_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6300010000050001'0d0a2db40000000049454e44ae426082"
    .replace("'", "")
)


def section(name):
    global _section
    _section = name
    print(f"\n{'=' * 70}\n{name}\n{'=' * 70}")


def check(label, condition, detail=""):
    if condition:
        PASSED.append(f"{_section} :: {label}")
        print(f"  PASS  {label}")
    else:
        FAILED.append(f"{_section} :: {label} {detail}")
        print(f"  FAIL  {label}  {detail}")
    return condition


def req(method, path, token=None, **kwargs):
    headers = kwargs.pop("headers", {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return requests.request(method, f"{BASE}{path}", headers=headers,
                            timeout=TIMEOUT, **kwargs)


def login(username, password):
    r = req("POST", "/api/auth/login", json={"username": username, "password": password})
    return r.json().get("token") if r.status_code == 200 else None


# ---------------------------------------------------------------------------
def test_health():
    section("1. HEALTH & SUBSYSTEMS")
    r = req("GET", "/api/health")
    check("health returns 200", r.status_code == 200)
    body = r.json()
    check("database subsystem is up", body["subsystems"]["database"] is True,
          f"got {body['subsystems']}")
    check("threat model loaded", body["subsystems"]["threat_model"] is True)
    check("version reported", body.get("version") == "2.0.0")
    for header, expected in [("X-Content-Type-Options", "nosniff"),
                             ("X-Frame-Options", "DENY"),
                             ("Referrer-Policy", "no-referrer")]:
        check(f"security header {header}", r.headers.get(header) == expected)


def test_registration():
    section("2. REGISTRATION VALIDATION")
    unique = uuid.uuid4().hex[:8]

    r = req("POST", "/api/auth/register",
            json={"username": f"e2e_{unique}", "password": "Str0ng#Pass1"})
    check("valid registration -> 201", r.status_code == 201, f"got {r.status_code}")

    r = req("POST", "/api/auth/register",
            json={"username": f"e2e_{unique}", "password": "Str0ng#Pass1"})
    check("duplicate username -> 409", r.status_code == 409, f"got {r.status_code}")

    cases = [
        ("username too short", {"username": "ab", "password": "Str0ng#Pass1"}, 422),
        ("username with space", {"username": "has space", "password": "Str0ng#Pass1"}, 422),
        ("username with symbol", {"username": "bad$name", "password": "Str0ng#Pass1"}, 422),
        ("password too short", {"username": f"x{unique}", "password": "Ab1!"}, 400),
        ("password letters only", {"username": f"y{unique}", "password": "onlyletters"}, 400),
        ("password digits only", {"username": f"z{unique}", "password": "1234567890"}, 400),
        ("password over 72 bytes", {"username": f"w{unique}", "password": "aB1" * 30}, 400),
        ("privilege escalation to admin",
         {"username": f"esc{unique}", "password": "Str0ng#Pass1", "role": "admin"}, 422),
        ("missing password", {"username": f"m{unique}"}, 400),
        ("empty body", {}, 422),
    ]
    for label, payload, expected in cases:
        r = req("POST", "/api/auth/register", json=payload)
        check(f"{label} -> {expected}", r.status_code == expected, f"got {r.status_code}")

    # Multibyte passwords are counted in bytes, not characters.
    r = req("POST", "/api/auth/register",
            json={"username": f"uni{unique}", "password": "Pässwörd#2024"})
    check("unicode password accepted", r.status_code == 201, f"got {r.status_code}")


def test_login_and_roles():
    section("3. LOGIN & ROLE MATRIX")
    tokens = {}
    for username, password, role in [
        ("analyst.rao", "Kestrel$Vale21", "analyst"),
        ("cmdr.hayes", "Falcon#Ridge77", "commander"),
        ("sysadmin.chen", "Onyx!Harbor44", "admin"),
    ]:
        token = login(username, password)
        check(f"login {role} ({username})", token is not None)
        tokens[role] = token
        if token:
            r = req("GET", "/api/auth/me", token=token)
            check(f"{role} /me role correct",
                  r.status_code == 200 and r.json()["user"]["role"] == role,
                  f"got {r.text[:80]}")

    check("wrong password -> 401", login("analyst.rao", "WrongPass#99") is None)
    check("unknown user -> 401", login("ghost.user", "Whatever#12") is None)

    # Identical response for both, so account existence cannot be probed.
    a = req("POST", "/api/auth/login", json={"username": "analyst.rao", "password": "Bad#1234"})
    b = req("POST", "/api/auth/login", json={"username": "nobody.here", "password": "Bad#1234"})
    check("user enumeration prevented",
          a.status_code == b.status_code and a.json()["message"] == b.json()["message"])

    # Role matrix: audit log is commander/admin only.
    matrix = [("analyst", 403), ("commander", 200), ("admin", 200)]
    for role, expected in matrix:
        r = req("GET", "/api/auth/audit-log", token=tokens.get(role))
        check(f"audit-log as {role} -> {expected}", r.status_code == expected,
              f"got {r.status_code}")

    return tokens


def test_auth_enforcement():
    section("4. AUTH ENFORCEMENT")
    endpoints = [
        ("GET", "/api/threats/history"), ("POST", "/api/threats/detect"),
        ("POST", "/api/predict/score"), ("GET", "/api/predict/forecast"),
        ("GET", "/api/predict/history"), ("POST", "/api/assistant/ask"),
        ("POST", "/api/assistant/report"), ("GET", "/api/data/map-markers"),
        ("GET", "/api/data/analytics"), ("GET", "/api/data/download-report"),
        ("GET", "/api/auth/audit-log"), ("GET", "/api/auth/me"),
    ]
    for method, path in endpoints:
        check(f"{method} {path} unauthenticated -> 401",
              req(method, path).status_code == 401)

    bad_tokens = [
        ("garbage", "not-a-token"),
        ("empty", ""),
        ("malformed jwt", "aaa.bbb.ccc"),
        ("alg-none forgery",
         "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0."
         "eyJ1c2VyX2lkIjoiZXZpbCIsInJvbGUiOiJhZG1pbiIsImV4cCI6OTk5OTk5OTk5OSwiaWF0IjoxfQ."),
    ]
    for label, token in bad_tokens:
        check(f"{label} token rejected",
              req("GET", "/api/auth/me", token=token).status_code == 401)


def test_scoring(token):
    section("5. THREAT SCORING & VALIDATION")
    base = {"object": "Tank", "confidence": 90, "weather": "Clear",
            "terrain": "Urban", "time_of_day": "Morning", "distance_km": 10}

    r = req("POST", "/api/predict/score", token=token, json=base)
    check("valid score -> 200", r.status_code == 200, f"got {r.status_code}")
    if r.status_code == 200:
        d = r.json()
        check("result persisted", d.get("persisted") is True)
        check("has score and level",
              0 <= d["data"]["ml_output"]["threat_score"] <= 99
              and d["data"]["ml_output"]["threat_level"] in
              {"LOW", "MEDIUM", "HIGH", "CRITICAL"})

    # Determinism: identical input must give identical score.
    s1 = req("POST", "/api/predict/score", token=token, json=base).json()["data"]["ml_output"]["threat_score"]
    s2 = req("POST", "/api/predict/score", token=token, json=base).json()["data"]["ml_output"]["threat_score"]
    check("scoring is deterministic", s1 == s2, f"{s1} vs {s2}")

    # Monotonicity sanity checks.
    def score(**over):
        p = dict(base); p.update(over)
        return req("POST", "/api/predict/score", token=token, json=p).json()["data"]["ml_output"]["threat_score"]

    check("Tank outranks Civilian Car", score(object="Tank") > score(object="Civilian Car"))
    check("closer contact scores higher", score(distance_km=1) > score(distance_km=45))
    check("higher confidence scores higher", score(confidence=99) > score(confidence=50))
    check("terrain affects score",
          len({score(terrain=t) for t in ["Desert", "Urban", "Forest", "Mountain"]}) > 1)

    invalid = [
        ("COCO class 'Person'", {"object": "Person"}, 422),
        ("unknown object", {"object": "Godzilla"}, 422),
        ("negative distance", {"distance_km": -99999}, 422),
        ("distance beyond range", {"distance_km": 99999}, 422),
        ("confidence over 100", {"confidence": 10_000_000}, 422),
        ("confidence negative", {"confidence": -5}, 422),
        ("string distance", {"distance_km": "abc"}, 422),
        ("boolean confidence", {"confidence": True}, 422),
        ("null object", {"object": None}, 422),
        ("array as object", {"object": ["Tank"]}, 422),
        ("invalid weather", {"weather": "Sharknado"}, 422),
        ("invalid terrain", {"terrain": "Moon"}, 422),
        ("NaN distance", {"distance_km": float("nan")}, 422),
    ]
    for label, override, expected in invalid:
        payload = dict(base); payload.update(override)
        try:
            r = req("POST", "/api/predict/score", token=token,
                    data=json.dumps(payload), headers={"Content-Type": "application/json"})
        except ValueError:
            r = req("POST", "/api/predict/score", token=token, json=payload)
        check(f"{label} -> {expected}", r.status_code == expected, f"got {r.status_code}")
        if r.status_code == 422:
            body = r.text.lower()
            check(f"{label} leaks no internals",
                  not any(w in body for w in ["dmatrix", "dataframe", "traceback", "xgboost"]))


def test_uploads(token):
    section("6. UPLOAD SECURITY")
    cases = [
        ("text file", b"hello world", "notes.txt", 422),
        ("disguised .jpg", b"still plain text", "payload.jpg", 422),
        ("svg", b"<svg xmlns='http://www.w3.org/2000/svg'/>", "logo.svg", 422),
        ("empty png", b"", "empty.png", 422),
        ("no extension", b"\x89PNG\r\n\x1a\n", "noext", 422),
        ("php double extension", b"<?php echo 1; ?>", "shell.php.png", 422),
        ("path traversal name", TINY_PNG, "../../../etc/passwd.png", (200, 503)),
        ("valid tiny png", TINY_PNG, "frame.png", (200, 503)),
    ]
    for label, content, filename, expected in cases:
        r = req("POST", "/api/threats/detect", token=token,
                files={"image": (filename, io.BytesIO(content), "application/octet-stream")})
        ok = r.status_code in (expected if isinstance(expected, tuple) else (expected,))
        check(f"{label} -> {expected}", ok, f"got {r.status_code}")

    r = req("POST", "/api/threats/detect", token=token)
    check("missing file -> 422", r.status_code == 422, f"got {r.status_code}")

    oversized = TINY_PNG + b"\x00" * (11 * 1024 * 1024)
    r = req("POST", "/api/threats/detect", token=token,
            files={"image": ("big.png", io.BytesIO(oversized), "image/png")})
    check("oversized upload -> 413", r.status_code == 413, f"got {r.status_code}")


def test_data_endpoints(token):
    section("7. DATA & ANALYTICS")
    r = req("GET", "/api/predict/history?limit=10", token=token)
    check("prediction history -> 200", r.status_code == 200)
    body = r.json()
    check("returns records", len(body["data"]) > 0)
    check("respects limit", len(body["data"]) <= 10)
    check("reports total", body["pagination"]["total"] >= len(body["data"]))

    check("limit clamped to 100",
          req("GET", "/api/predict/history?limit=99999", token=token)
          .json()["pagination"]["limit"] == 100)
    check("garbage limit handled",
          req("GET", "/api/predict/history?limit=abc", token=token).status_code == 200)
    check("negative skip handled",
          req("GET", "/api/predict/history?skip=-5", token=token).status_code == 200)

    # Pagination must not repeat records.
    p1 = req("GET", "/api/predict/history?limit=5&skip=0", token=token).json()["data"]
    p2 = req("GET", "/api/predict/history?limit=5&skip=5", token=token).json()["data"]
    ids1 = {x["id"] for x in p1}; ids2 = {x["id"] for x in p2}
    check("pagination pages are disjoint", not (ids1 & ids2))

    r = req("GET", "/api/data/analytics", token=token)
    check("analytics -> 200", r.status_code == 200)
    a = r.json()
    check("analytics available with data", a.get("available") is True, str(a)[:120])
    if a.get("available"):
        check("object breakdown populated", len(a["object_breakdown"]) > 0)
        check("sector risk populated", len(a["sector_risk"]) > 0)
        check("risk values in range",
              all(0 <= s["risk"] <= 100 for s in a["sector_risk"]))

    r = req("GET", "/api/predict/forecast", token=token)
    f = r.json()["forecast"]
    check("forecast available", f.get("available") is True)
    if f.get("available"):
        check("forecast has sample size", f.get("sample_size", 0) > 0)
        check("border risk is a valid band",
              f.get("border_risk") in {"LOW", "MEDIUM", "HIGH", "CRITICAL"})
        check("shares sum sensibly",
              0 <= f.get("aerial_activity_share", 0) <= 100)

    r = req("GET", "/api/data/map-markers", token=token)
    check("map markers -> 200", r.status_code == 200)
    m = r.json()
    check("markers present", len(m["markers"]) > 0)
    check("markers in AO (eastern hemisphere)",
          all(71 < mk["lng"] < 74 and 33 < mk["lat"] < 35 for mk in m["markers"]),
          "coordinates outside area of operations")


def test_reports(token):
    section("8. REPORTS")
    r = req("GET", "/api/data/download-report", token=token)
    check("pdf -> 200", r.status_code == 200)
    check("content type is pdf", r.headers.get("content-type", "").startswith("application/pdf"))
    check("valid PDF header", r.content[:5] == b"%PDF-")
    check("pdf has EOF marker", b"%%EOF" in r.content[-1024:])
    check("pdf non-trivial size", len(r.content) > 2000, f"{len(r.content)} bytes")

    r = req("POST", "/api/assistant/report", token=token)
    check("assistant report -> 200", r.status_code == 200)
    if r.status_code == 200:
        d = r.json()
        check("report persisted", d.get("persisted") is True)
        check("offline mode labelled honestly",
              d["online"] is True or "OFFLINE MODE" in d["content"])
        check("no fabricated score in offline mode",
              d["online"] is True or "Score: 91" not in d["content"])


def test_assistant(token):
    section("9. ASSISTANT")
    r = req("POST", "/api/assistant/ask", token=token, json={"question": "Summarise activity"})
    check("ask -> 200", r.status_code == 200)
    check("empty question -> 422",
          req("POST", "/api/assistant/ask", token=token,
              json={"question": "   "}).status_code == 422)
    check("overlong question -> 422",
          req("POST", "/api/assistant/ask", token=token,
              json={"question": "x" * 5000}).status_code == 422)
    check("status endpoint public",
          req("GET", "/api/assistant/status").status_code == 200)


def test_errors_and_concurrency(token):
    section("10. ERROR HANDLING & CONCURRENCY")
    r = req("GET", "/api/nonexistent")
    check("unknown route -> JSON 404",
          r.status_code == 404 and r.headers["content-type"].startswith("application/json"))
    check("wrong method -> 405", req("GET", "/api/auth/login").status_code == 405)
    r = req("POST", "/api/predict/score", token=token, data="{bad json",
            headers={"Content-Type": "application/json"})
    check("malformed JSON handled", r.status_code == 422, f"got {r.status_code}")

    # Concurrent duplicate registration: the unique index must win the race.
    name = f"race_{uuid.uuid4().hex[:8]}"
    payload = {"username": name, "password": "Str0ng#Pass1"}
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = [f.result().status_code
                   for f in [pool.submit(req, "POST", "/api/auth/register", None,
                                         json=payload) for _ in range(6)]]
    check("exactly one concurrent registration succeeds",
          results.count(201) == 1, f"statuses {results}")
    check("the rest conflict with 409",
          results.count(409) == len(results) - 1, f"statuses {results}")

    # Sustained load smoke test.
    start = time.time()
    codes = []
    with ThreadPoolExecutor(max_workers=10) as pool:
        codes = [f.result().status_code for f in
                 [pool.submit(req, "GET", "/api/health") for _ in range(40)]]
    elapsed = time.time() - start
    check("40 concurrent health checks all 200", all(c == 200 for c in codes))
    check(f"throughput acceptable ({elapsed:.1f}s)", elapsed < 25, f"{elapsed:.1f}s")


def main():
    global BASE
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=BASE)
    args = parser.parse_args()
    BASE = args.base

    print(f"AegisAI end-to-end test suite -> {BASE}")
    try:
        requests.get(f"{BASE}/api/health", timeout=10)
    except requests.RequestException as exc:
        print(f"Backend unreachable: {exc}")
        return 1

    test_health()
    test_registration()
    tokens = test_login_and_roles()
    test_auth_enforcement()
    token = tokens.get("analyst") or tokens.get("admin")
    test_scoring(token)
    test_uploads(token)
    test_data_endpoints(token)
    test_reports(token)
    test_assistant(token)
    test_errors_and_concurrency(token)

    print(f"\n{'=' * 70}")
    print(f"RESULT: {len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("\nFailures:")
        for f in FAILED:
            print(f"  - {f}")
        return 1
    print("All end-to-end checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
