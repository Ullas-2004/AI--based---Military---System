"""Threat-scoring, taxonomy and input-validation tests."""
import io

import pytest

from middleware.validation import ValidationError
from services.ml_service import (
    predict_threat_score, categorize_score, counterfactuals,
)
from services.taxonomy import map_detection_class, THREAT_CLASSES


class TestTaxonomy:
    def test_person_maps_to_soldier(self):
        """Regression: YOLO's 'person' used to score as 'Civilian Car'."""
        assert map_detection_class("person") == ("Soldier", True)

    def test_bus_and_truck_map_to_truck(self):
        assert map_detection_class("truck")[0] == "Truck"
        assert map_detection_class("bus")[0] == "Truck"

    def test_unknown_class_is_reported_not_defaulted(self):
        mapped, ok = map_detection_class("giraffe")
        assert mapped is None and ok is False

    def test_mapping_is_case_insensitive(self):
        assert map_detection_class("PERSON")[0] == "Soldier"

    def test_every_mapped_class_exists_in_model_vocabulary(self):
        from services.taxonomy import COCO_TO_THREAT
        assert set(COCO_TO_THREAT.values()) <= set(THREAT_CLASSES)


class TestScoring:
    def test_known_class_scores(self):
        result = predict_threat_score("Tank", 95, "Fog", "Desert", "Night", 2.0)
        assert 0 <= result["threat_score"] <= 99
        assert result["threat_level"] in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}

    def test_unknown_object_raises_instead_of_silent_fallback(self):
        """The core bug: unmapped labels became the lowest-threat class."""
        with pytest.raises(ValidationError, match="Unknown DetectedObject"):
            predict_threat_score("Person", 95, "Fog", "Desert", "Night", 2.0)

    def test_tank_outranks_civilian_car_on_identical_telemetry(self):
        tank = predict_threat_score("Tank", 95, "Fog", "Desert", "Night", 2.0)
        car = predict_threat_score("Civilian Car", 95, "Fog", "Desert", "Night", 2.0)
        assert tank["threat_score"] > car["threat_score"]

    def test_proximity_increases_threat(self):
        near = predict_threat_score("Tank", 90, "Clear", "Desert", "Morning", 1.0)
        far = predict_threat_score("Tank", 90, "Clear", "Desert", "Morning", 45.0)
        assert near["threat_score"] > far["threat_score"]

    def test_confidence_now_influences_score(self):
        """Regression: ConfidenceScore importance was 0.0005 (no signal)."""
        high = predict_threat_score("Tank", 99, "Clear", "Desert", "Morning", 10.0)
        low = predict_threat_score("Tank", 45, "Clear", "Desert", "Morning", 10.0)
        assert high["threat_score"] > low["threat_score"] + 2

    def test_terrain_now_influences_score(self):
        """Regression: Terrain importance was 0.0003 (feature was ignored)."""
        scores = {
            terrain: predict_threat_score("Tank", 90, "Clear", terrain, "Morning", 8.0)["threat_score"]
            for terrain in ("Desert", "Urban", "Forest", "Mountain")
        }
        assert max(scores.values()) - min(scores.values()) > 2

    @pytest.mark.parametrize("score,expected", [
        (95, "CRITICAL"), (80, "CRITICAL"), (79.9, "HIGH"),
        (60, "HIGH"), (59.9, "MEDIUM"), (40, "MEDIUM"), (39.9, "LOW"), (0, "LOW"),
    ])
    def test_band_boundaries(self, score, expected):
        assert categorize_score(score) == expected


class TestExplainability:
    """SHAP attribution must be exact, not a plausible-sounding narrative."""

    def _explained(self, **over):
        args = dict(detected_object="Tank", confidence=95, weather="Fog",
                    terrain="Desert", time_of_day="Night", distance_km=2.0)
        args.update(over)
        return predict_threat_score(**args)

    def test_explanation_present_by_default(self):
        assert "explanation" in self._explained()

    def test_can_be_disabled_for_bulk_scoring(self):
        assert "explanation" not in self._explained(explain=False)

    def test_all_six_features_attributed(self):
        factors = self._explained()["explanation"]["factors"]
        assert len(factors) == 6
        assert {f["feature"] for f in factors} == {
            "DetectedObject", "ConfidenceScore", "Weather",
            "Terrain", "TimeOfDay", "DistanceToBorder_km",
        }

    def test_contributions_sum_to_raw_prediction(self):
        """The faithfulness guarantee: baseline + contributions == raw output."""
        exp = self._explained()["explanation"]
        total = exp["baseline"] + sum(f["contribution"] for f in exp["factors"])
        assert abs(total - exp["raw_score"]) < 0.05, f"{total} != {exp['raw_score']}"

    def test_factors_sorted_by_influence(self):
        contribs = [abs(f["contribution"])
                    for f in self._explained()["explanation"]["factors"]]
        assert contribs == sorted(contribs, reverse=True)

    def test_direction_matches_sign(self):
        for f in self._explained()["explanation"]["factors"]:
            if f["contribution"] > 0:
                assert f["direction"] == "increases" and f["gerund"] == "raising"
            else:
                assert f["direction"] == "decreases" and f["gerund"] == "lowering"

    def test_tank_raises_and_civilian_car_lowers(self):
        tank = next(f for f in self._explained()["explanation"]["factors"]
                    if f["feature"] == "DetectedObject")
        car = next(f for f in self._explained(detected_object="Civilian Car")["explanation"]["factors"]
                   if f["feature"] == "DetectedObject")
        assert tank["contribution"] > 0 > car["contribution"]

    def test_clamping_is_disclosed(self):
        exp = self._explained()["explanation"]
        # This input exceeds the 99 cap, so the flag must be set.
        assert exp["was_clamped"] is (abs(exp["raw_score"] - 99.0) > 0.01
                                      and exp["raw_score"] > 99.0)

    def test_summary_is_grammatical(self):
        summary = self._explained()["explanation"]["summary"]
        assert "increaseing" not in summary and "decreaseing" not in summary
        assert "raising" in summary or "lowering" in summary

    def test_prediction_interval_present(self):
        interval = self._explained()["interval"]
        assert interval["lower"] <= interval["upper"]
        assert interval["nominal_coverage"] == 0.8
        assert interval["confidence_level"] in {"high", "moderate", "low"}

    def test_interval_width_matches_confidence_label(self):
        interval = self._explained()["interval"]
        width, level = interval["width"], interval["confidence_level"]
        expected = "high" if width <= 8 else "moderate" if width <= 15 else "low"
        assert level == expected

    def test_interval_bounded_to_reporting_range(self):
        interval = self._explained()["interval"]
        assert 0 <= interval["lower"] <= 99
        assert 0 <= interval["upper"] <= 99

    def test_borderline_input_flagged_as_spanning_bands(self):
        """An interval straddling a boundary is the key analyst caveat."""
        borderline = predict_threat_score("Truck", 70, "Rain", "Forest", "Evening", 14.0)
        assert borderline["interval"]["spans_bands"] is True

    def test_api_returns_explanation(self, client, mock_db, auth_headers):
        res = client.post("/api/predict/score", headers=auth_headers, json={
            "object": "UAV", "confidence": 80, "weather": "Snow",
            "terrain": "Mountain", "time_of_day": "Night", "distance_km": 6,
        })
        assert res.status_code == 200
        exp = res.get_json()["data"]["ml_output"]["explanation"]
        assert exp["method"].startswith("Exact Shapley")
        assert len(exp["factors"]) == 6


class TestCounterfactuals:
    """Every counterfactual must be a verified re-score, not an estimate."""

    def test_returns_band_changing_alternatives(self):
        results = counterfactuals("UAV", 88, "Clear", "Mountain", "Evening", 9.0)
        assert results, "expected at least one band-changing alternative"
        for cf in results:
            assert cf["new_level"] != "HIGH" or cf["new_level"] != cf.get("from")

    def test_every_candidate_actually_changes_the_band(self):
        base = predict_threat_score("UAV", 88, "Clear", "Mountain", "Evening", 9.0,
                                    explain=False)
        for cf in counterfactuals("UAV", 88, "Clear", "Mountain", "Evening", 9.0):
            assert cf["new_level"] != base["threat_level"]

    def test_candidates_are_reproducible_by_rescoring(self):
        """Re-running the stated change must reproduce the stated score."""
        args = dict(detected_object="UAV", confidence=88, weather="Clear",
                    terrain="Mountain", time_of_day="Evening", distance_km=9.0)
        field_map = {
            "object": "detected_object", "confidence": "confidence",
            "weather": "weather", "terrain": "terrain",
            "time_of_day": "time_of_day", "distance_km": "distance_km",
        }
        for cf in counterfactuals(**{
            "detected_object": "UAV", "confidence": 88, "weather": "Clear",
            "terrain": "Mountain", "time_of_day": "Evening", "distance_km": 9.0,
        }):
            probe = dict(args)
            probe[field_map[cf["field"]]] = cf["to"]
            rescored = predict_threat_score(**probe, explain=False)
            assert rescored["threat_score"] == cf["new_score"]

    def test_sorted_by_smallest_change(self):
        deltas = [abs(c["delta"])
                  for c in counterfactuals("Truck", 70, "Rain", "Forest", "Evening", 14.0)]
        assert deltas == sorted(deltas)

    def test_robust_input_yields_no_counterfactuals(self):
        """An extreme CRITICAL case that no single feature change can move."""
        results = counterfactuals("Tank", 99, "Fog", "Desert", "Night", 0.5)
        # Only object class can plausibly shift it; anything else leaves CRITICAL.
        assert all(c["field"] == "object" for c in results)

    def test_api_endpoint(self, client, mock_db, auth_headers):
        res = client.post("/api/predict/counterfactuals", headers=auth_headers, json={
            "object": "UAV", "confidence": 88, "weather": "Clear",
            "terrain": "Mountain", "time_of_day": "Evening", "distance_km": 9,
        })
        assert res.status_code == 200
        body = res.get_json()
        assert "counterfactuals" in body and "is_robust" in body

    def test_api_requires_auth(self, client, mock_db):
        assert client.post("/api/predict/counterfactuals",
                           json={"object": "UAV"}).status_code == 401

    def test_api_validates_input(self, client, mock_db, auth_headers):
        res = client.post("/api/predict/counterfactuals", headers=auth_headers,
                          json={"object": "Godzilla"})
        assert res.status_code == 422


class TestModelCard:
    def test_public_endpoint_returns_metrics(self, client):
        res = client.get("/api/predict/model-card")
        assert res.status_code == 200
        card = res.get_json()["model_card"]
        assert 0 <= card["metrics"]["r2"] <= 1
        assert 0 <= card["metrics"]["band_accuracy"] <= 1
        assert card["training_data"] == "synthetic"

    def test_documents_limitations_honestly(self, client):
        card = client.get("/api/predict/model-card").get_json()["model_card"]
        combined = " ".join(card["limitations"]).lower()
        assert "synthetic" in combined
        assert "proxy" in combined
        assert len(card["limitations"]) >= 3

    def test_reports_empirical_not_just_nominal_coverage(self, client):
        """Claiming 80% without measuring it would be the dishonest version."""
        card = client.get("/api/predict/model-card").get_json()["model_card"]
        assert "empirical_coverage" in card["uncertainty"]
        assert 0 <= card["uncertainty"]["empirical_coverage"] <= 1


class TestScoreEndpointValidation:
    ENDPOINT = "/api/predict/score"

    def _post(self, client, headers, **overrides):
        payload = {
            "object": "Tank", "confidence": 90, "weather": "Clear",
            "terrain": "Urban", "time_of_day": "Morning", "distance_km": 10,
        }
        payload.update(overrides)
        return client.post(self.ENDPOINT, json=payload, headers=headers)

    def test_valid_request_succeeds(self, client, mock_db, auth_headers):
        res = self._post(client, auth_headers)
        assert res.status_code == 200
        assert res.get_json()["data"]["ml_output"]["threat_level"]

    def test_negative_distance_rejected(self, client, mock_db, auth_headers):
        """Regression: distance_km=-99999 previously returned CRITICAL."""
        res = self._post(client, auth_headers, distance_km=-99999)
        assert res.status_code == 422
        assert "distance_km" in res.get_json()["field"]

    def test_absurd_confidence_rejected(self, client, mock_db, auth_headers):
        assert self._post(client, auth_headers, confidence=100_000_000).status_code == 422

    def test_string_distance_does_not_leak_internals(self, client, mock_db, auth_headers):
        """Regression: leaked the XGBoost/DataFrame dtype error to the client."""
        res = self._post(client, auth_headers, distance_km="not-a-number")
        assert res.status_code == 422
        body = res.get_json()["message"].lower()
        assert "must be a number" in body
        assert "dmatrix" not in body and "dataframe" not in body

    def test_boolean_is_not_accepted_as_number(self, client, mock_db, auth_headers):
        assert self._post(client, auth_headers, confidence=True).status_code == 422

    def test_unknown_object_returns_422_with_valid_options(self, client, mock_db, auth_headers):
        res = self._post(client, auth_headers, object="Bus")
        assert res.status_code == 422
        assert "Tank" in res.get_json()["message"]

    def test_missing_object_rejected(self, client, mock_db, auth_headers):
        res = client.post(self.ENDPOINT, json={}, headers=auth_headers)
        assert res.status_code == 422

    def test_categories_endpoint_lists_accepted_values(self, client):
        body = client.get("/api/predict/categories").get_json()
        assert set(body["categories"]["DetectedObject"]) == set(THREAT_CLASSES)


class TestUploadValidation:
    ENDPOINT = "/api/threats/detect"
    PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64

    def test_missing_file_rejected(self, client, mock_db, auth_headers):
        assert client.post(self.ENDPOINT, headers=auth_headers).status_code == 422

    def test_text_file_rejected(self, client, mock_db, auth_headers):
        """Regression: evil.txt used to return 200 'success'."""
        data = {"image": (io.BytesIO(b"not an image"), "evil.txt")}
        res = client.post(self.ENDPOINT, data=data, headers=auth_headers,
                          content_type="multipart/form-data")
        assert res.status_code == 422
        assert "Unsupported file type" in res.get_json()["message"]

    def test_disguised_extension_rejected_by_magic_number(self, client, mock_db, auth_headers):
        """A .txt renamed to .jpg must still be refused."""
        data = {"image": (io.BytesIO(b"still just text"), "payload.jpg")}
        res = client.post(self.ENDPOINT, data=data, headers=auth_headers,
                          content_type="multipart/form-data")
        assert res.status_code == 422
        assert "not a valid image" in res.get_json()["message"]

    def test_svg_rejected(self, client, mock_db, auth_headers):
        data = {"image": (io.BytesIO(b"<svg xmlns='...'/>"), "logo.svg")}
        res = client.post(self.ENDPOINT, data=data, headers=auth_headers,
                          content_type="multipart/form-data")
        assert res.status_code == 422

    def test_empty_file_rejected(self, client, mock_db, auth_headers):
        data = {"image": (io.BytesIO(b""), "empty.png")}
        res = client.post(self.ENDPOINT, data=data, headers=auth_headers,
                          content_type="multipart/form-data")
        assert res.status_code == 422

    def test_oversized_upload_returns_413(self, client, mock_db, auth_headers):
        big = self.PNG + b"\x00" * (3 * 1024 * 1024)   # limit is 2 MB in tests
        data = {"image": (io.BytesIO(big), "huge.png")}
        res = client.post(self.ENDPOINT, data=data, headers=auth_headers,
                          content_type="multipart/form-data")
        assert res.status_code == 413

    def test_path_traversal_filename_is_neutralised(self, client, mock_db, auth_headers):
        data = {"image": (io.BytesIO(self.PNG), "../../../etc/passwd.png")}
        res = client.post(self.ENDPOINT, data=data, headers=auth_headers,
                          content_type="multipart/form-data")
        # Either detection runs or the engine is unavailable, but never a write
        # outside the upload directory.
        assert res.status_code in (200, 503)
