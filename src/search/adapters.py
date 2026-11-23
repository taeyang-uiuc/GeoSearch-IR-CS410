"""Adapters that connect the hybrid coordinator to team-owned components."""

from __future__ import annotations

import json
from pathlib import Path

from .hybrid_search import BM25Hit, FilteredBM25Searcher, SpatialCandidateProvider


def load_jsonl_metadata(jsonl_path: str | Path) -> dict[str, dict[str, object]]:
    """Load display and coordinate fields from the prepared Lucene JSONL file."""

    metadata: dict[str, dict[str, object]] = {}
    with Path(jsonl_path).open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            document = json.loads(line)
            missing_fields = {"id", "lat", "lon"} - document.keys()
            if missing_fields:
                missing = ", ".join(sorted(missing_fields))
                raise ValueError(f"JSONL line {line_number} is missing: {missing}")

            restaurant_id = str(document["id"])
            if restaurant_id in metadata:
                raise ValueError(f"Duplicate restaurant id in JSONL: {restaurant_id}")
            metadata[restaurant_id] = {
                "business_id": restaurant_id,
                "name": str(document.get("name", "")),
                "address": str(document.get("address", "")),
                "latitude": float(document["lat"]),
                "longitude": float(document["lon"]),
            }
    return metadata


def rtree_candidate_provider(
    index,
    restaurants,
    metadata_by_id: dict[str, dict[str, object]] | None = None,
) -> SpatialCandidateProvider:
    """Adapt Swarvanu's R-tree index and DataFrame to the integration API.

    The existing R-tree helper returns a latitude/longitude bounding-box result.
    ``search_restaurants`` performs the exact great-circle radius check after
    this adapter returns the records.
    """

    from src.geo.create_geo_index import query_nearby

    def candidates(
        latitude: float,
        longitude: float,
        radius_meters: float,
    ) -> list[dict[str, object]]:
        nearby = query_nearby(index, restaurants, latitude, longitude, radius_meters)
        records = nearby.to_dict(orient="records")
        if metadata_by_id is None:
            return records

        enriched_records: list[dict[str, object]] = []
        for record in records:
            restaurant_id = str(record["business_id"])
            enriched = dict(record)
            enriched.update(metadata_by_id.get(restaurant_id, {}))
            enriched_records.append(enriched)
        return enriched_records

    return candidates


def pyserini_filtered_bm25_search(searcher) -> FilteredBM25Searcher:
    """Adapt a Pyserini LuceneSearcher to filtered BM25 retrieval.

    The prepared JSONL uses ``id`` for the restaurant identifier and
    ``contents`` for indexed text. Pyserini retains ``id`` as the external
    document identifier used by this filter and by returned hits.
    """

    return _pyserini_searcher(searcher, id_field="id")


def _pyserini_searcher(searcher, *, id_field: str) -> FilteredBM25Searcher:
    def search(
        query: str,
        allowed_ids: set[str],
        top_k: int,
    ) -> list[BM25Hit]:
        if not allowed_ids:
            return []

        try:
            from pyserini.pyclass import autoclass
        except ImportError as error:
            raise RuntimeError(
                "Pyserini is required for Lucene filtered retrieval. "
                "Install it after the BM25 index is available."
            ) from error

        boolean_query = autoclass("org.apache.lucene.search.BooleanQuery$Builder")
        term_in_set_query = autoclass("org.apache.lucene.search.TermInSetQuery")
        boolean_clause = autoclass("org.apache.lucene.search.BooleanClause")
        bytes_ref = autoclass("org.apache.lucene.util.BytesRef")

        identifier_terms = [bytes_ref(value.encode()) for value in sorted(allowed_ids)]
        identifier_filter = term_in_set_query(id_field, identifier_terms)
        text_query = searcher.object.buildQuery(query)

        builder = boolean_query()
        builder.add(text_query, boolean_clause.Occur.valueOf("MUST"))
        builder.add(identifier_filter, boolean_clause.Occur.valueOf("FILTER"))

        hits = searcher.object.search(builder.build(), top_k)
        return [BM25Hit(hit.docid, float(hit.score)) for hit in hits]

    return search
