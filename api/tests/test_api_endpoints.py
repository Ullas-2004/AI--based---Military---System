"""Endpoint behaviour, error handling and serialization tests."""
from datetime import datetime, timezone

from utils.serialization import serialize_doc, parse_pagination


class TestHealth:
    def test_reports_subsystems(self, client):
        body = client.get("/api/health").get_json()
        assert body["status"] == "success"
        assert set(body["subsystems"]) == {"database", "threat_model", "assistant"}
        assert body["subsystems"]["threat_model"] is True

    def test_security_headers_present(self, client):
        headers = client.get("/api/health").headers
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert headers["X-Frame-Options"] == "DENY"


class TestErrorHandling:
    def test_unknown_route_returns_json_not_html(self, client):
        """Regression: 404s used to return a Werkzeug HTML page."""
        res = client.get("/api/does-not-exist")
        assert res.status_code == 404
        assert res.content_type.startswith("application/json")
        assert res.get_json()["status"] == "error"

    def test_wrong_method_returns_json_405(self, client):
        res = client.get("/api/auth/login")
        assert res.status_code == 405
        assert res.get_json()["status"] == "error"

    def test_malformed_json_body_is_handled(self, client, mock_db, auth_headers):
        res = client.post("/api/predict/score", data="{not json",
                          content_type="application/json", headers=auth_headers)
        assert res.status_code == 422


class TestAssistant:
    def test_status_public_and_offline_without_key(self, client):
        assert client.get("/api/assistant/status").get_json()["online"] is False

    def test_offline_mode_does_not_fabricate_scores(self, client, mock_db, auth_headers):
        """Regression: the mock invented 'CRITICAL (Score: 91)' out of thin air."""
        body = client.post("/api/assistant/ask", json={"question": "status?"},
                           headers=auth_headers).get_json()
        assert body["online"] is False
        assert "OFFLINE MODE" in body["answer"]
        assert "Score: 91" not in body["answer"]

    def test_empty_question_rejected(self, client, mock_db, auth_headers):
        res = client.post("/api/assistant/ask", json={"question": "   "},
                          headers=auth_headers)
        assert res.status_code == 422

    def test_report_persists_and_returns_id(self, client, mock_db, auth_headers):
        body = client.post("/api/assistant/report", headers=auth_headers).get_json()
        assert body["persisted"] is True
        assert body["report_id"]
        assert mock_db.intelligence_reports.count_documents({}) == 1


class TestDataHub:
    def test_map_markers_use_the_same_area_as_the_map(self, client, mock_db, auth_headers):
        """Regression: API returned Los Angeles, the UI rendered Pakistan."""
        body = client.get("/api/data/map-markers", headers=auth_headers).get_json()
        assert body["is_demo"] is True
        for marker in body["markers"]:
            assert 33.0 < marker["lat"] < 35.0
            assert 71.0 < marker["lng"] < 74.0   # eastern hemisphere

    def test_analytics_reports_unavailable_rather_than_inventing(self, client, mock_db, auth_headers):
        body = client.get("/api/data/analytics", headers=auth_headers).get_json()
        assert body["available"] is False
        assert body["trend"] == []

    def test_analytics_aggregates_real_records(self, client, mock_db, auth_headers):
        client.post("/api/predict/score", headers=auth_headers, json={
            "object": "Tank", "confidence": 90, "weather": "Fog",
            "terrain": "Desert", "time_of_day": "Night", "distance_km": 3,
        })
        body = client.get("/api/data/analytics", headers=auth_headers).get_json()
        assert body["available"] is True
        assert any(item["name"] == "Tank" for item in body["object_breakdown"])

    def test_pdf_export_returns_a_pdf(self, client, mock_db, auth_headers):
        res = client.get("/api/data/download-report", headers=auth_headers)
        assert res.status_code == 200
        assert res.mimetype == "application/pdf"
        assert res.data[:5] == b"%PDF-"

    def test_pdf_export_writes_nothing_to_disk(self, client, mock_db, auth_headers):
        """Reports render in memory; an on-disk temp file would accumulate."""
        import os
        from config import config

        before = set(os.listdir(config.UPLOAD_FOLDER)) if os.path.isdir(config.UPLOAD_FOLDER) else set()
        client.get("/api/data/download-report", headers=auth_headers)
        after = set(os.listdir(config.UPLOAD_FOLDER)) if os.path.isdir(config.UPLOAD_FOLDER) else set()
        assert before == after

    def test_pdf_escapes_untrusted_database_content(self, client, mock_db, auth_headers):
        mock_db.threat_predictions.insert_one({
            "telemetry": {"object": "<b>inject</b>", "terrain": "Urban", "distance_km": 1.0},
            "ml_output": {"threat_score": 50, "threat_level": "MEDIUM"},
            "created_at": datetime.now(timezone.utc),
        })
        res = client.get("/api/data/download-report", headers=auth_headers)
        assert res.status_code == 200 and res.data[:5] == b"%PDF-"


class TestForecast:
    def test_says_insufficient_data_when_empty(self, client, mock_db, auth_headers):
        """Regression: forecast used to return hardcoded '78%' percentages."""
        body = client.get("/api/predict/forecast", headers=auth_headers).get_json()
        assert body["forecast"]["available"] is False

    def test_computes_from_stored_predictions(self, client, mock_db, auth_headers):
        for _ in range(3):
            client.post("/api/predict/score", headers=auth_headers, json={
                "object": "UAV", "confidence": 88, "weather": "Clear",
                "terrain": "Mountain", "time_of_day": "Night", "distance_km": 5,
            })
        forecast = client.get("/api/predict/forecast",
                              headers=auth_headers).get_json()["forecast"]
        assert forecast["available"] is True
        assert forecast["sample_size"] == 3
        assert forecast["aerial_activity_share"] == 100.0


class TestAnalystReview:
    """Human-in-the-loop verdicts and the metrics derived from them."""

    def _seed(self, mock_db, status="pending_analyst_review"):
        return mock_db.vision_detections.insert_one({
            "original_filename": "frame.jpg", "detections": [],
            "unmapped_detections": [], "total_objects": 1,
            "model": "yolov8n", "status": status,
            "created_at": datetime.now(timezone.utc),
        }).inserted_id

    def test_confirm_detection(self, client, mock_db, auth_headers):
        oid = self._seed(mock_db)
        res = client.post(f"/api/threats/{oid}/review", headers=auth_headers,
                          json={"status": "confirmed", "note": "verified"})
        assert res.status_code == 200
        stored = mock_db.vision_detections.find_one({"_id": oid})
        assert stored["status"] == "confirmed"
        assert stored["review"]["note"] == "verified"
        assert stored["review"]["reviewed_by"] == "user-1"

    def test_mark_false_positive(self, client, mock_db, auth_headers):
        oid = self._seed(mock_db)
        res = client.post(f"/api/threats/{oid}/review", headers=auth_headers,
                          json={"status": "false_positive"})
        assert res.status_code == 200
        assert mock_db.vision_detections.find_one({"_id": oid})["status"] == "false_positive"

    def test_review_is_reversible(self, client, mock_db, auth_headers):
        oid = self._seed(mock_db, "confirmed")
        client.post(f"/api/threats/{oid}/review", headers=auth_headers,
                    json={"status": "pending_analyst_review"})
        assert mock_db.vision_detections.find_one({"_id": oid})["status"] == "pending_analyst_review"

    def test_requires_auth(self, client, mock_db):
        oid = self._seed(mock_db)
        assert client.post(f"/api/threats/{oid}/review",
                           json={"status": "confirmed"}).status_code == 401

    def test_invalid_status_rejected(self, client, mock_db, auth_headers):
        oid = self._seed(mock_db)
        res = client.post(f"/api/threats/{oid}/review", headers=auth_headers,
                          json={"status": "definitely_a_tank"})
        assert res.status_code == 422

    def test_malformed_id_rejected(self, client, mock_db, auth_headers):
        res = client.post("/api/threats/not-an-objectid/review",
                          headers=auth_headers, json={"status": "confirmed"})
        assert res.status_code == 422

    def test_unknown_id_returns_404(self, client, mock_db, auth_headers):
        from bson import ObjectId
        res = client.post(f"/api/threats/{ObjectId()}/review",
                          headers=auth_headers, json={"status": "confirmed"})
        assert res.status_code == 404

    def test_overlong_note_rejected(self, client, mock_db, auth_headers):
        oid = self._seed(mock_db)
        res = client.post(f"/api/threats/{oid}/review", headers=auth_headers,
                          json={"status": "confirmed", "note": "x" * 600})
        assert res.status_code == 422

    def test_metrics_reflect_verdicts(self, client, mock_db, auth_headers):
        for status in ["confirmed", "confirmed", "false_positive",
                       "pending_analyst_review"]:
            self._seed(mock_db, status)
        m = client.get("/api/threats/review-metrics",
                       headers=auth_headers).get_json()["metrics"]
        assert m["confirmed"] == 2
        assert m["false_positive"] == 1
        assert m["false_positive_rate"] == round(100 * 1 / 3, 1)

    def test_false_positive_rate_is_null_when_nothing_reviewed(
            self, client, mock_db, auth_headers):
        """Null, not 0.0 — 'no data' must not read as 'no false positives'."""
        self._seed(mock_db)
        m = client.get("/api/threats/review-metrics",
                       headers=auth_headers).get_json()["metrics"]
        assert m["false_positive_rate"] is None

    def test_review_is_audited(self, client, mock_db, auth_headers):
        oid = self._seed(mock_db)
        client.post(f"/api/threats/{oid}/review", headers=auth_headers,
                    json={"status": "confirmed"})
        assert mock_db.audit_logs.count_documents({"action": "DETECTION_REVIEWED"}) == 1


class TestPagination:
    def test_limit_is_clamped(self):
        assert parse_pagination({"limit": "100000"})[0] == 100
        assert parse_pagination({"limit": "0"})[0] == 1
        assert parse_pagination({"limit": "abc"})[0] == 25

    def test_negative_skip_clamped_to_zero(self):
        assert parse_pagination({"skip": "-5"})[1] == 0

    def test_history_respects_limit(self, client, mock_db, auth_headers):
        for _ in range(6):
            client.post("/api/predict/score", headers=auth_headers, json={
                "object": "Truck", "confidence": 70, "weather": "Rain",
                "terrain": "Forest", "time_of_day": "Evening", "distance_km": 20,
            })
        body = client.get("/api/predict/history?limit=2", headers=auth_headers).get_json()
        assert len(body["data"]) == 2
        assert body["pagination"]["total"] == 6


class TestSerialization:
    def test_objectid_and_datetime_become_json_safe(self):
        from bson import ObjectId
        oid = ObjectId()
        out = serialize_doc({
            "_id": oid,
            "created_at": datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
            "nested": {"when": datetime(2026, 1, 1, tzinfo=timezone.utc), "ids": [oid]},
        })
        assert out["id"] == str(oid)
        assert out["created_at"].startswith("2026-01-02T03:04:05")
        assert out["nested"]["ids"] == [str(oid)]
        assert "_id" not in out
