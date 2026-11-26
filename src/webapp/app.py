"""Flask webapp for validating GeoSearch-IR hybrid search results."""

from __future__ import annotations

import json
from pathlib import Path

from flask import Flask, jsonify, render_template, request

BASE_DIR = Path(__file__).resolve().parents[2]
GEOJSON_PATH = BASE_DIR / "src/resources/restaurant_reviews.geojson"
CSV_PATH = BASE_DIR / "src/resources/restaurant_reviews.csv"
JSONL_PATH = BASE_DIR / "data/restaurants.jsonl"
INDEX_PATH = BASE_DIR / "geosearch_work/index"

app = Flask(__name__)

with GEOJSON_PATH.open(encoding="utf-8") as f:
    _geojson = json.load(f)

_all_restaurants = [
    {"lat": feat["geometry"]["coordinates"][1], "lon": feat["geometry"]["coordinates"][0], **feat["properties"]}
    for feat in _geojson["features"]
]


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/restaurants")
def restaurants():
    return jsonify(_all_restaurants)


@app.route("/api/search")
def search():
    query = request.args.get("query", "").strip()
    try:
        lat = float(request.args.get("lat"))
        lon = float(request.args.get("lon"))
        radius_miles = float(request.args.get("radius_miles", 25))
        top_k = int(request.args.get("top_k", 10))
    except (TypeError, ValueError) as e:
        return jsonify({"error": str(e)}), 400

    if not query:
        return jsonify({"error": "query is required"}), 400

    from src.geo.create_geo_index import build_rtree
    from src.search.adapters import (
        load_jsonl_metadata,
        pyserini_filtered_bm25_search,
        rtree_candidate_provider,
    )
    from src.search.hybrid_search import exponential_distance_decay, search_restaurants
    from src.text.bm25_search import open_searcher

    spatial_index, spatial_rows = build_rtree(str(CSV_PATH))
    metadata = load_jsonl_metadata(JSONL_PATH)
    spatial_candidates = rtree_candidate_provider(spatial_index, spatial_rows, metadata_by_id=metadata)
    lucene_searcher = open_searcher(INDEX_PATH)

    try:
        results = search_restaurants(
            query=query,
            user_latitude=lat,
            user_longitude=lon,
            radius_meters=radius_miles * 1609.344,
            spatial_candidates=spatial_candidates,
            bm25_search=pyserini_filtered_bm25_search(lucene_searcher),
            distance_decay=exponential_distance_decay(5 * 1609.344),
            candidate_limit=50,
            top_k=top_k,
        )
    finally:
        lucene_searcher.close()

    from dataclasses import asdict
    return jsonify([asdict(r) for r in results])


if __name__ == "__main__":
    app.run(debug=True, port=5000)
