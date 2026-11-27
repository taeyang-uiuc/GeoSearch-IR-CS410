"""End-to-end spatial filtering, BM25 retrieval, and distance reranking.

This module owns the integration boundary between the R-tree component and the
Lucene BM25 component. A caller supplies a spatial candidate provider and a
BM25 search function. The coordinator applies an exact geographic-radius check
before it passes candidate restaurant IDs to BM25, then reranks the returned
documents using a distance-decay score.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import asin, cos, exp, radians, sin, sqrt
from typing import Callable, Iterable, Mapping, Protocol, Sequence


EARTH_RADIUS_METERS = 6_371_008.8


@dataclass(frozen=True)
class BM25Hit:
    """One text-retrieval result returned by the BM25 component."""

    restaurant_id: str
    score: float


@dataclass(frozen=True)
class SearchResult:
    """A final ranked restaurant result with scores used for inspection."""

    restaurant_id: str
    name: str
    address: str
    distance_meters: float
    bm25_score: float
    spatial_score: float
    final_score: float


@dataclass(frozen=True)
class HybridSearchResult:
    """Both rankings returned by the hybrid pipeline."""

    bm25_ranking: list[SearchResult]
    hybrid_ranking: list[SearchResult]


class SpatialCandidateProvider(Protocol):
    """Returns broad spatial candidates with restaurant metadata."""

    def __call__(
        self,
        latitude: float,
        longitude: float,
        radius_meters: float,
    ) -> Iterable[Mapping[str, object]]: ...


class FilteredBM25Searcher(Protocol):
    """Ranks only the restaurant IDs passed through ``allowed_ids``."""

    def __call__(
        self,
        query: str,
        allowed_ids: set[str],
        top_k: int,
    ) -> Sequence[BM25Hit | tuple[str, float]]: ...


DistanceDecay = Callable[[float], float]


def haversine_meters(
    first_latitude: float,
    first_longitude: float,
    second_latitude: float,
    second_longitude: float,
) -> float:
    """Return the great-circle distance between two latitude/longitude points."""

    latitude_delta = radians(second_latitude - first_latitude)
    longitude_delta = radians(second_longitude - first_longitude)
    first_latitude_radians = radians(first_latitude)
    second_latitude_radians = radians(second_latitude)

    haversine_value = (
        sin(latitude_delta / 2) ** 2
        + cos(first_latitude_radians)
        * cos(second_latitude_radians)
        * sin(longitude_delta / 2) ** 2
    )
    return 2 * EARTH_RADIUS_METERS * asin(sqrt(haversine_value))


def exponential_distance_decay(scale_meters: float) -> DistanceDecay:
    """Create a score function whose value decays from 1 as distance increases."""

    if scale_meters <= 0:
        raise ValueError("scale_meters must be greater than zero")

    return lambda distance_meters: exp(-distance_meters / scale_meters)


def search_restaurants(
    query: str,
    user_latitude: float,
    user_longitude: float,
    radius_meters: float,
    spatial_candidates: SpatialCandidateProvider,
    bm25_search: FilteredBM25Searcher,
    distance_decay: DistanceDecay,
    *,
    candidate_limit: int = 20,
    top_k: int = 2,
    bm25_weight: float = 0.75,
    spatial_weight: float = 0.25,
) -> HybridSearchResult:
    """Run the GeoSearch-IR hybrid query pipeline.

    ``spatial_candidates`` may return a broad R-tree bounding-box result. This
    function performs the exact great-circle radius filter before it invokes
    BM25. Restaurant rows must contain ``business_id``, ``latitude``, and
    ``longitude``. ``name`` and ``address`` are optional display fields.
    """

    _validate_query_parameters(
        query=query,
        latitude=user_latitude,
        longitude=user_longitude,
        radius_meters=radius_meters,
        candidate_limit=candidate_limit,
        top_k=top_k,
        bm25_weight=bm25_weight,
        spatial_weight=spatial_weight,
    )

    candidates_by_id = _exact_radius_candidates(
        spatial_candidates(user_latitude, user_longitude, radius_meters),
        user_latitude,
        user_longitude,
        radius_meters,
    )
    if not candidates_by_id:
        return HybridSearchResult(bm25_ranking=[], hybrid_ranking=[])

    allowed_ids = set(candidates_by_id)
    bm25_hits = _coerce_bm25_hits(
        bm25_search(query, allowed_ids, candidate_limit),
        allowed_ids,
    )
    if not bm25_hits:
        return HybridSearchResult(bm25_ranking=[], hybrid_ranking=[])

    normalized_bm25 = _normalize_bm25_scores(bm25_hits)
    results: list[SearchResult] = []
    for hit in bm25_hits:
        candidate, distance_meters = candidates_by_id[hit.restaurant_id]
        spatial_score = _validated_spatial_score(distance_decay(distance_meters))
        final_score = (
            bm25_weight * normalized_bm25[hit.restaurant_id]
            + spatial_weight * spatial_score
        )
        results.append(
            SearchResult(
                restaurant_id=hit.restaurant_id,
                name=str(candidate.get("name", "")),
                address=str(candidate.get("address", "")),
                distance_meters=distance_meters,
                bm25_score=hit.score,
                spatial_score=spatial_score,
                final_score=final_score,
            )
        )

    hybrid_ranking = sorted(
        results,
        key=lambda result: (
            -result.final_score,
            -result.bm25_score,
            result.distance_meters,
            result.restaurant_id,
        ),
    )[:top_k]

    return HybridSearchResult(bm25_ranking=results, hybrid_ranking=hybrid_ranking)


def _exact_radius_candidates(
    candidates: Iterable[Mapping[str, object]],
    user_latitude: float,
    user_longitude: float,
    radius_meters: float,
) -> dict[str, tuple[Mapping[str, object], float]]:
    candidates_by_id: dict[str, tuple[Mapping[str, object], float]] = {}
    for candidate in candidates:
        restaurant_id = str(candidate["business_id"])
        latitude = float(candidate["latitude"])
        longitude = float(candidate["longitude"])
        distance_meters = haversine_meters(
            user_latitude,
            user_longitude,
            latitude,
            longitude,
        )
        if distance_meters <= radius_meters:
            existing = candidates_by_id.get(restaurant_id)
            if existing is None or distance_meters < existing[1]:
                candidates_by_id[restaurant_id] = (candidate, distance_meters)
    return candidates_by_id


def _coerce_bm25_hits(
    hits: Sequence[BM25Hit | tuple[str, float]],
    allowed_ids: set[str],
) -> list[BM25Hit]:
    accepted_hits: list[BM25Hit] = []
    seen_ids: set[str] = set()
    for hit in hits:
        restaurant_id, score = (
            (hit.restaurant_id, hit.score)
            if isinstance(hit, BM25Hit)
            else (str(hit[0]), float(hit[1]))
        )
        if restaurant_id in allowed_ids and restaurant_id not in seen_ids:
            accepted_hits.append(BM25Hit(restaurant_id, float(score)))
            seen_ids.add(restaurant_id)
    return accepted_hits


def _normalize_bm25_scores(hits: Sequence[BM25Hit]) -> dict[str, float]:
    scores = [hit.score for hit in hits]
    minimum = min(scores)
    maximum = max(scores)
    if maximum == minimum:
        return {hit.restaurant_id: 1.0 for hit in hits}
    return {
        hit.restaurant_id: (hit.score - minimum) / (maximum - minimum)
        for hit in hits
    }


def _validated_spatial_score(score: float) -> float:
    if not 0.0 <= score <= 1.0:
        raise ValueError("distance_decay must return a score from 0 through 1")
    return score


def _validate_query_parameters(
    *,
    query: str,
    latitude: float,
    longitude: float,
    radius_meters: float,
    candidate_limit: int,
    top_k: int,
    bm25_weight: float,
    spatial_weight: float,
) -> None:
    if not query.strip():
        raise ValueError("query must not be empty")
    if not -90 <= latitude <= 90:
        raise ValueError("latitude must be between -90 and 90")
    if not -180 <= longitude <= 180:
        raise ValueError("longitude must be between -180 and 180")
    if radius_meters <= 0:
        raise ValueError("radius_meters must be greater than zero")
    if candidate_limit <= 0 or top_k <= 0:
        raise ValueError("candidate_limit and top_k must be greater than zero")
    if bm25_weight < 0 or spatial_weight < 0:
        raise ValueError("ranking weights must not be negative")
    if bm25_weight + spatial_weight == 0:
        raise ValueError("at least one ranking weight must be positive")
