import unittest
import json
import tempfile
from pathlib import Path

from src.search.adapters import load_jsonl_metadata
from src.search.hybrid_search import BM25Hit, exponential_distance_decay, search_restaurants


class HybridSearchTests(unittest.TestCase):
    def setUp(self):
        self.candidates = [
            {
                "business_id": "nearby-text-match",
                "name": "Nearby Cafe",
                "address": "1 Main St",
                "latitude": 40.0005,
                "longitude": -88.0000,
            },
            {
                "business_id": "farther-text-match",
                "name": "Farther Cafe",
                "address": "2 Main St",
                "latitude": 40.0050,
                "longitude": -88.0000,
            },
            {
                "business_id": "outside-radius",
                "name": "Outside Cafe",
                "address": "3 Main St",
                "latitude": 40.0500,
                "longitude": -88.0000,
            },
        ]

    def test_filters_before_bm25_and_reranks_by_distance(self):
        received_allowed_ids = set()

        def spatial_candidates(latitude, longitude, radius_meters):
            return self.candidates

        def bm25_search(query, allowed_ids, top_k):
            received_allowed_ids.update(allowed_ids)
            return [
                BM25Hit("farther-text-match", 10.0),
                BM25Hit("nearby-text-match", 9.0),
                BM25Hit("outside-radius", 100.0),
            ]

        results = search_restaurants(
            "coffee",
            user_latitude=40.0,
            user_longitude=-88.0,
            radius_meters=1_000,
            spatial_candidates=spatial_candidates,
            bm25_search=bm25_search,
            distance_decay=exponential_distance_decay(150),
            bm25_weight=0.1,
            spatial_weight=0.9,
        )

        self.assertEqual(
            received_allowed_ids,
            {"nearby-text-match", "farther-text-match"},
        )
        self.assertEqual([result.restaurant_id for result in results], [
            "nearby-text-match",
            "farther-text-match",
        ])
        self.assertLess(results[0].distance_meters, results[1].distance_meters)

    def test_returns_no_results_without_spatial_candidates(self):
        results = search_restaurants(
            "coffee",
            user_latitude=40.0,
            user_longitude=-88.0,
            radius_meters=1_000,
            spatial_candidates=lambda latitude, longitude, radius: [],
            bm25_search=lambda query, ids, limit: [BM25Hit("unexpected", 1.0)],
            distance_decay=exponential_distance_decay(150),
        )

        self.assertEqual(results, [])

    def test_loads_prepared_jsonl_fields_for_result_metadata(self):
        document = {
            "id": "restaurant-1",
            "contents": "quiet cafe with outdoor seating",
            "name": "Test Cafe",
            "address": "1 Main St",
            "lat": 40.1,
            "lon": -88.2,
        }
        with tempfile.TemporaryDirectory() as directory:
            jsonl_path = Path(directory) / "restaurants.jsonl"
            jsonl_path.write_text(json.dumps(document) + "\n", encoding="utf-8")
            metadata = load_jsonl_metadata(jsonl_path)

        self.assertEqual(metadata["restaurant-1"]["business_id"], "restaurant-1")
        self.assertEqual(metadata["restaurant-1"]["name"], "Test Cafe")
        self.assertEqual(metadata["restaurant-1"]["latitude"], 40.1)


if __name__ == "__main__":
    unittest.main()
