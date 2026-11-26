"""Regressions for the visualization app's JSON error contract."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.webapp import app as web


class WebAppTests(unittest.TestCase):
    def setUp(self):
        self.client = web.app.test_client()

    def test_invalid_search_parameters_return_json_before_loading_search(self):
        cases = [
            {"lat": "91"}, {"lon": "181"}, {"lat": "nan"},
            {"lon": "inf"}, {"radius_miles": "-1"},
            {"radius_miles": "nan"}, {"top_k": "0"}, {"top_k": "51"},
            {"top_k": "1.5"}, {"query": " "}, {"lat": ""},
        ]
        with patch.object(web, "_spatial_candidates") as load_search:
            for overrides in cases:
                params = {"query": "pizza", "lat": "36.12", "lon": "-115.17"}
                params.update(overrides)
                with self.subTest(overrides=overrides):
                    response = self.client.get("/api/search", query_string=params)
                    self.assertEqual(response.status_code, 400)
                    self.assertIn("error", response.get_json())
            load_search.assert_not_called()

    def test_missing_index_returns_actionable_json_error(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(web, "INDEX_PATH", Path(directory) / "absent"):
                response = self.client.get("/api/search", query_string={
                    "query": "pizza", "lat": 36.12, "lon": -115.17,
                })
        self.assertEqual(response.status_code, 503)
        self.assertIn("--build-only", response.get_json()["error"])

    def test_search_failure_keeps_json_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            index = Path(directory)
            (index / "segments_1").touch()
            with patch.object(web, "INDEX_PATH", index), patch.object(
                web, "_spatial_candidates", side_effect=RuntimeError("unavailable")
            ), patch.object(web.app.logger, "exception"):
                response = self.client.get("/api/search", query_string={
                    "query": "pizza", "lat": 36.12, "lon": -115.17,
                })
        self.assertEqual(response.status_code, 500)
        self.assertIn("error", response.get_json())
