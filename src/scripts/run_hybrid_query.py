"""Run one end-to-end GeoSearch-IR query from the command line.

Run from the repository root after the Lucene index is available:

    python -m src.scripts.run_hybrid_query \
        --lucene-index geosearch_work/index \
        --query "quiet restaurant with outdoor seating" \
        --latitude 36.12 --longitude -115.17
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from src.search.adapters import (
    load_jsonl_metadata,
    pyserini_filtered_bm25_search,
    rtree_candidate_provider,
)
from src.search.hybrid_search import exponential_distance_decay, search_restaurants
from src.text.bm25_search import INPUT_FILE, WORK_DIR, open_searcher


METERS_PER_MILE = 1_609.344


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a hybrid restaurant query")
    parser.add_argument("--query", required=True, help="Natural-language restaurant preference")
    parser.add_argument("--latitude", required=True, type=float, help="User latitude")
    parser.add_argument("--longitude", required=True, type=float, help="User longitude")
    parser.add_argument("--lucene-index", type=Path, default=WORK_DIR / "index")
    parser.add_argument("--csv", default="src/resources/restaurant_reviews.csv")
    parser.add_argument("--jsonl", type=Path, default=INPUT_FILE)
    parser.add_argument("--radius-miles", type=float, default=25.0)
    parser.add_argument("--decay-scale-miles", type=float, default=5.0)
    parser.add_argument("--candidate-limit", type=int, default=20)
    parser.add_argument("--top-k", type=int, default=2)
    parser.add_argument("--bm25-weight", type=float, default=0.75)
    parser.add_argument("--spatial-weight", type=float, default=0.25)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.lucene_index.is_dir():
        raise SystemExit(
            f"Lucene index not found at {args.lucene_index}. "
            "Build it with python -m src.text.bm25_search --build-only."
        )

    from src.geo.create_geo_index import build_rtree

    spatial_index, spatial_rows = build_rtree(args.csv)
    metadata = load_jsonl_metadata(args.jsonl)
    spatial_candidates = rtree_candidate_provider(
        spatial_index,
        spatial_rows,
        metadata_by_id=metadata,
    )
    lucene_searcher = open_searcher(args.lucene_index)

    try:
        results = search_restaurants(
            query=args.query,
            user_latitude=args.latitude,
            user_longitude=args.longitude,
            radius_meters=args.radius_miles * METERS_PER_MILE,
            spatial_candidates=spatial_candidates,
            bm25_search=pyserini_filtered_bm25_search(lucene_searcher),
            distance_decay=exponential_distance_decay(
                args.decay_scale_miles * METERS_PER_MILE
            ),
            candidate_limit=args.candidate_limit,
            top_k=args.top_k,
            bm25_weight=args.bm25_weight,
            spatial_weight=args.spatial_weight,
        )
    finally:
        lucene_searcher.close()

    print(json.dumps([asdict(result) for result in results], indent=2))


if __name__ == "__main__":
    main()
