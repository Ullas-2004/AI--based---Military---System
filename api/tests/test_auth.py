"""Authentication, authorisation and password-handling tests."""
import pytest

from middleware.auth import (
    AuthError, hash_password, verify_password, generate_token, decode_token,
    validate_password,
)


class TestPasswordHandling:
    def test_roundtrip(self):
        hashed = hash_password("Correct-Horse-9")
        assert verify_password("Correct-Horse-9", hashed)
        assert not verify_password("wrong-password-1", hashed)

    def test_over_72_bytes_raises_authError_not_500(self):
        """Regression: bcrypt's 72-byte cap used to surface as an HTTP 500."""
        with pytest.raises(AuthError, match="72 bytes"):
            hash_password("a1" * 40)  # 80 bytes

    def test_multibyte_password_counted_in_bytes(self):
        # 30 characters but 60 bytes: allowed. 40 characters/80 bytes: rejected.
        hash_password("é1" * 15)
        with pytest.raises(AuthError, match="72 bytes"):
            hash_password("é1" * 40)

    def test_verify_never_raises_on_overlong_candidate(self):
        hashed = hash_password("Correct-Horse-9")
        assert verify_password("x" * 500, hashed) is False

    def test_verify_handles_corrupt_hash(self):
        assert verify_password("anything1", "not-a-bcrypt-hash") is False

    @pytest.mark.parametrize("bad", ["", "short1", "alllettersonly", "12345678901"])
    def test_weak_passwords_rejected(self, bad):
        with pytest.raises(AuthError):
            validate_password(bad)


class TestTokens:
    def test_roundtrip_carries_claims(self):
        decoded = decode_token(generate_token("user-9", "commander"))
        assert decoded["user_id"] == "user-9"
        assert decoded["role"] == "commander"

    def test_tampered_token_rejected(self):
        token = generate_token("user-9", "analyst")
        assert decode_token(token[:-4] + "aaaa")["error"] == "Invalid token"

    def test_token_signed_with_other_key_rejected(self):
        import jwt
        forged = jwt.encode(
            {"user_id": "evil", "role": "admin", "exp": 9999999999, "iat": 1},
            "attacker-key", algorithm="HS256",
        )
        assert "error" in decode_token(forged)

    def test_alg_none_rejected(self):
        """The algorithm is pinned, so an unsigned token must not be accepted."""
        import jwt
        forged = jwt.encode(
            {"user_id": "evil", "role": "admin", "exp": 9999999999, "iat": 1},
            key="", algorithm="none",
        )
        assert "error" in decode_token(forged)

    def test_expired_token_reported_as_expired(self):
        import jwt
        from config import config
        expired = jwt.encode(
            {"user_id": "u", "role": "analyst", "exp": 1000, "iat": 900},
            config.JWT_SECRET_KEY, algorithm="HS256",
        )
        assert decode_token(expired)["error"] == "Token expired"


class TestRegistrationAndLogin:
    def test_register_then_login(self, client, mock_db):
        reg = client.post("/api/auth/register",
                          json={"username": "analyst1", "password": "Str0ngPass!"})
        assert reg.status_code == 201

        login = client.post("/api/auth/login",
                            json={"username": "analyst1", "password": "Str0ngPass!"})
        assert login.status_code == 200
        assert login.get_json()["token"]

    def test_duplicate_username_conflicts(self, client, mock_db):
        payload = {"username": "dupe", "password": "Str0ngPass!"}
        assert client.post("/api/auth/register", json=payload).status_code == 201
        assert client.post("/api/auth/register", json=payload).status_code == 409

    def test_login_is_case_insensitive_on_username(self, client, mock_db):
        client.post("/api/auth/register",
                    json={"username": "MixedCase", "password": "Str0ngPass!"})
        res = client.post("/api/auth/login",
                          json={"username": "mixedcase", "password": "Str0ngPass!"})
        assert res.status_code == 200

    def test_unknown_user_and_wrong_password_are_indistinguishable(self, client, mock_db):
        client.post("/api/auth/register",
                    json={"username": "real", "password": "Str0ngPass!"})
        wrong = client.post("/api/auth/login",
                            json={"username": "real", "password": "Wr0ngPass!"})
        missing = client.post("/api/auth/login",
                              json={"username": "ghost", "password": "Wr0ngPass!"})
        assert wrong.status_code == missing.status_code == 401
        assert wrong.get_json()["message"] == missing.get_json()["message"]

    def test_overlong_password_returns_400_not_500(self, client, mock_db):
        res = client.post("/api/auth/register",
                          json={"username": "bigpw", "password": "a1" * 40})
        assert res.status_code == 400
        assert "72 bytes" in res.get_json()["message"]

    def test_cannot_self_register_as_admin(self, client, mock_db):
        res = client.post("/api/auth/register",
                          json={"username": "sneaky", "password": "Str0ngPass!",
                                "role": "admin"})
        assert res.status_code == 422

    @pytest.mark.parametrize("username", ["ab", "has space", "sym$bol", "x" * 40])
    def test_invalid_usernames_rejected(self, client, mock_db, username):
        res = client.post("/api/auth/register",
                          json={"username": username, "password": "Str0ngPass!"})
        assert res.status_code == 422


class TestRouteProtection:
    PROTECTED = [
        ("get", "/api/threats/history"),
        ("post", "/api/threats/detect"),
        ("post", "/api/predict/score"),
        ("get", "/api/predict/forecast"),
        ("get", "/api/predict/history"),
        ("post", "/api/assistant/ask"),
        ("post", "/api/assistant/report"),
        ("get", "/api/data/map-markers"),
        ("get", "/api/data/analytics"),
        ("get", "/api/data/download-report"),
        ("get", "/api/auth/audit-log"),
        ("get", "/api/auth/me"),
    ]

    @pytest.mark.parametrize("method,path", PROTECTED)
    def test_requires_token(self, client, method, path):
        """Regression: every one of these was publicly readable."""
        assert getattr(client, method)(path).status_code == 401

    @pytest.mark.parametrize("method,path", PROTECTED)
    def test_rejects_garbage_token(self, client, method, path):
        res = getattr(client, method)(path, headers={"Authorization": "Bearer nonsense"})
        assert res.status_code == 401

    def test_audit_log_forbidden_for_analyst(self, client, mock_db, auth_headers):
        assert client.get("/api/auth/audit-log", headers=auth_headers).status_code == 403

    def test_audit_log_allowed_for_admin(self, client, mock_db, admin_headers):
        assert client.get("/api/auth/audit-log", headers=admin_headers).status_code == 200

    def test_health_is_public(self, client):
        assert client.get("/api/health").status_code == 200


class TestRateLimiting:
    """Credential stuffing is the main brute-force exposure on this API."""

    def test_login_throttled_after_limit(self, client, mock_db, monkeypatch):
        from config import config
        monkeypatch.setattr(config, "RATE_LIMIT_LOGIN", 3)
        monkeypatch.setattr(config, "RATE_LIMIT_LOGIN_WINDOW", 60)

        codes = [client.post("/api/auth/login",
                             json={"username": "someone", "password": "Wr0ng#Pass"}).status_code
                 for _ in range(6)]
        assert codes[:3] == [401, 401, 401]
        assert codes[3:] == [429, 429, 429]

    def test_429_includes_retry_after(self, client, mock_db, monkeypatch):
        from config import config
        monkeypatch.setattr(config, "RATE_LIMIT_LOGIN", 1)
        client.post("/api/auth/login", json={"username": "a", "password": "Wr0ng#Pass"})
        res = client.post("/api/auth/login", json={"username": "a", "password": "Wr0ng#Pass"})
        assert res.status_code == 429
        assert int(res.headers["Retry-After"]) > 0
        assert "Too many requests" in res.get_json()["message"]

    def test_successful_responses_carry_limit_headers(self, client, mock_db, monkeypatch):
        from config import config
        monkeypatch.setattr(config, "RATE_LIMIT_LOGIN", 5)
        res = client.post("/api/auth/login", json={"username": "a", "password": "Wr0ng#Pass"})
        assert res.headers["X-RateLimit-Limit"] == "5"
        assert int(res.headers["X-RateLimit-Remaining"]) == 4

    def test_can_be_disabled(self, client, mock_db, monkeypatch):
        from config import config
        monkeypatch.setattr(config, "RATE_LIMIT_ENABLED", False)
        monkeypatch.setattr(config, "RATE_LIMIT_LOGIN", 1)
        codes = [client.post("/api/auth/login",
                             json={"username": "a", "password": "Wr0ng#Pass"}).status_code
                 for _ in range(4)]
        assert 429 not in codes

    def test_protected_endpoints_are_not_throttled(self, client, mock_db, auth_headers):
        """Rate limiting belongs on unauthenticated abuse paths, not normal use."""
        codes = [client.get("/api/predict/forecast", headers=auth_headers).status_code
                 for _ in range(15)]
        assert 429 not in codes
