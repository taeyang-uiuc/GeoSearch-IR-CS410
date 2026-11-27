"""Flask webapp for validating GeoSearch-IR hybrid search results."""

from __future__ import annotations

import json
from dataclasses import asdict
from functools import lru_cache
from math import isfinite
from pathlib import Path
from threading import Lock

from flask import Flask, jsonify, render_template, request

BASE_DIR = Path(__file__).resolve().parents[2]
GEOJSON_PATH = BASE_DIR / "src/resources/restaurant_reviews.geojson"
CSV_PATH = BASE_DIR / "src/resources/restaurant_reviews.csv"
JSONL_PATH = BASE_DIR / "data/restaurants.jsonl"
INDEX_PATH = BASE_DIR / "geosearch_work/index"

app = Flask(__name__)
_search_lock = Lock()

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
    except (TypeError, ValueError):
        return jsonify({"error": "lat, lon, and radius must be numbers; top_k must be an integer"}), 400

    if not query:
        return jsonify({"error": "query is required"}), 400
    if not isfinite(lat) or not -90 <= lat <= 90:
        return jsonify({"error": "latitude must be between -90 and 90"}), 400
    if not isfinite(lon) or not -180 <= lon <= 180:
        return jsonify({"error": "longitude must be between -180 and 180"}), 400
    if not isfinite(radius_miles) or radius_miles <= 0:
        return jsonify({"error": "radius must be a positive finite number"}), 400
    if not 1 <= top_k <= 50:
        return jsonify({"error": "top_k must be between 1 and 50"}), 400
    if not (INDEX_PATH / "segments.gen").exists() and not any(INDEX_PATH.glob("segments_*")):
        return jsonify({"error": "Lucene index is missing. Run python -m src.text.bm25_search --build-only, then restart the server."}), 503

    try:
        candidate_limit = int(request.args.get("candidate_limit", 50))
    except (TypeError, ValueError):
        return jsonify({"error": "candidate_limit must be an integer"}), 400

    from src.search.adapters import pyserini_filtered_bm25_search
    from src.search.hybrid_search import exponential_distance_decay, search_restaurants
    from src.text.bm25_search import open_searcher

    radius_meters = radius_miles * 1609.344

    try:
        with _search_lock:
            spatial_candidates = _spatial_candidates()
            lucene_searcher = open_searcher(INDEX_PATH)
            try:
                result = search_restaurants(
                    query=query,
                    user_latitude=lat,
                    user_longitude=lon,
                    radius_meters=radius_meters,
                    spatial_candidates=spatial_candidates,
                    bm25_search=pyserini_filtered_bm25_search(lucene_searcher),
                    distance_decay=exponential_distance_decay(5 * 1609.344),
                    candidate_limit=candidate_limit,
                    top_k=candidate_limit,
                )
            finally:
                lucene_searcher.close()
    except Exception:
        app.logger.exception("Hybrid search failed")
        return jsonify({"error": "Search failed. Check the server log and the Python/Java environment, then verify the Lucene index."}), 500

    return jsonify({
        "bm25_ranking": [asdict(r) for r in result.bm25_ranking],
        "hybrid_ranking": [asdict(r) for r in result.hybrid_ranking],
    })


@lru_cache(maxsize=1)
def _spatial_candidates():
    """Build immutable spatial inputs once per server process."""

    from src.geo.create_geo_index import build_rtree
    from src.search.adapters import (
        load_jsonl_metadata,
        rtree_candidate_provider,
    )

    spatial_index, spatial_rows = build_rtree(str(CSV_PATH))
    metadata = load_jsonl_metadata(JSONL_PATH)
    return rtree_candidate_provider(spatial_index, spatial_rows, metadata_by_id=metadata)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
