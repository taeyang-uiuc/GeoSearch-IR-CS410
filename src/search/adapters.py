"""Adapters that connect the hybrid coordinator to team-owned components."""

from __future__ import annotations

from .hybrid_search import BM25Hit, FilteredBM25Searcher, SpatialCandidateProvider


def rtree_candidate_provider(index, restaurants) -> SpatialCandidateProvider:
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
        return nearby.to_dict(orient="records")

    return candidates


def pyserini_filtered_bm25_search(searcher) -> FilteredBM25Searcher:
    """Adapt a Pyserini LuceneSearcher to filtered BM25 retrieval.

    The Lucene index must store the dataset restaurant ID in a string field
    named ``business_id``. If the index uses a different field name, change
    ``id_field`` below when creating the adapter.
    """

    return _pyserini_searcher(searcher, id_field="business_id")


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
