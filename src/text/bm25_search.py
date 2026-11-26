"""Build and query a Lucene BM25 index over the prepared restaurant JSONL."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory


REPO_ROOT = Path(__file__).resolve().parents[2]
INPUT_FILE = REPO_ROOT / "data/restaurants.jsonl"
WORK_DIR = REPO_ROOT / "geosearch_work"
TOP_K = 10
BM25_K1, BM25_B = 0.9, 0.4
SNIPPET_CHARS = 160


def clean_text(text):
    """The reviews contain literal backslash-n sequences; turn them into spaces."""
    return " ".join(str(text).replace("\\n", " ").split())


def build_index(input_file, work_dir=WORK_DIR, *, rebuild=False):
    """Clean the JSONL and build the index before replacing any existing one."""
    work_dir = Path(work_dir).resolve()
    index_dir = work_dir / "index"
    if index_dir.exists() and not rebuild:
        raise FileExistsError(f"{index_dir} already exists. Use --rebuild to replace it.")
    work_dir.mkdir(parents=True, exist_ok=True)

    with TemporaryDirectory(prefix="build-", dir=work_dir) as staging:
        staging = Path(staging)
        docs_dir = staging / "docs"
        docs_dir.mkdir()
        pending_index = staging / "index"
        count = 0
        with open(input_file, encoding="utf-8") as source, (docs_dir / "docs.jsonl").open(
            "w", encoding="utf-8"
        ) as output:
            for line in source:
                if not line.strip():
                    continue
                record = json.loads(line)
                contents = clean_text(record.get("contents", ""))
                if contents:
                    output.write(json.dumps({"id": str(record["id"]), "contents": contents}) + "\n")
                    count += 1

        if not count:
            raise ValueError(f"No indexable documents found in {input_file}.")
        print(f"Indexing {count} documents ...", flush=True)
        subprocess.run(
            [
                sys.executable, "-m", "pyserini.index.lucene",
                "--collection", "JsonCollection",
                "--input", str(docs_dir),
                "--index", str(pending_index),
                "--generator", "DefaultLuceneDocumentGenerator",
                "--threads", "1",
                "--storePositions", "--storeDocvectors", "--storeRaw",
            ],
            check=True,
        )

        previous_index = staging / "previous-index"
        if rebuild and index_dir.exists():
            index_dir.rename(previous_index)
        try:
            pending_index.rename(index_dir)
        except OSError:
            if previous_index.exists():
                previous_index.rename(index_dir)
            raise

    print(f"Index built at {index_dir}")
    return str(index_dir)


def load_metadata(input_file):
    """id -> {name, address, lat, lon, contents} for display and later hybrid ranking."""
    meta = {}
    with open(input_file, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                meta[str(r["id"])] = {
                    "name": r.get("name", ""),
                    "address": r.get("address", ""),
                    "lat": r.get("lat"),
                    "lon": r.get("lon"),
                    "contents": clean_text(r.get("contents", "")),
                }
    return meta


def open_searcher(index_dir):
    """Open a searcher using the same BM25 settings for both retrieval modes."""
    # Some Pyserini versions initialize an OpenAI client during import.
    os.environ.setdefault("OPENAI_API_KEY", "unused-by-local-bm25")
    from pyserini.search.lucene import LuceneSearcher

    searcher = LuceneSearcher(str(index_dir))
    searcher.set_bm25(k1=BM25_K1, b=BM25_B)
    return searcher


def search_hits(searcher, query, top_k, allowed_ids=None):
    """Return Lucene hits, optionally restricting by external document ID."""
    if allowed_ids is None:
        return searcher.search(query, top_k)
    if not allowed_ids:
        return []

    from jnius import autoclass

    array_list = autoclass("java.util.ArrayList")
    bytes_ref = autoclass("org.apache.lucene.util.BytesRef")
    term_in_set = autoclass("org.apache.lucene.search.TermInSetQuery")
    occur = autoclass("org.apache.lucene.search.BooleanClause$Occur")
    builder = autoclass("org.apache.lucene.search.BooleanQuery$Builder")()
    query_generator = autoclass("io.anserini.search.query.BagOfWordsQueryGenerator")()

    terms = array_list()
    for restaurant_id in sorted(allowed_ids):
        terms.add(bytes_ref(restaurant_id.encode("utf-8")))
    text_query = query_generator.buildQuery("contents", searcher.object.get_analyzer(), query)
    builder.add(text_query, occur.MUST)
    builder.add(term_in_set("id", terms), occur.FILTER)
    return searcher.search(builder.build(), top_k)


def bm25_search(meta, index_dir, query, top_k=TOP_K, allowed_ids=None):
    """Return ranked results with restaurant metadata for the text-only demo."""
    searcher = open_searcher(index_dir)
    try:
        return _format_hits(meta, search_hits(searcher, query, top_k, allowed_ids))
    finally:
        searcher.close()


def _format_hits(meta, hits):
    results = []
    for hit in hits:
        record = meta.get(hit.docid, {})
        results.append({
            "id": hit.docid,
            "score": float(hit.score),
            "name": record.get("name", ""),
            "address": record.get("address", ""),
            "lat": record.get("lat"),
            "lon": record.get("lon"),
            "snippet": record.get("contents", "")[:SNIPPET_CHARS],
        })
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_file", nargs="?", type=Path, default=INPUT_FILE)
    parser.add_argument("--work-dir", type=Path, default=WORK_DIR)
    parser.add_argument("--build-only", action="store_true")
    parser.add_argument("--rebuild", action="store_true")
    args = parser.parse_args()

    index_dir = args.work_dir / "index"
    if args.rebuild or not index_dir.is_dir():
        build_index(args.input_file, args.work_dir, rebuild=args.rebuild)
    else:
        print(f"Using existing index at {index_dir} (use --rebuild to re-index).")

    if args.build_only:
        return

    meta = load_metadata(args.input_file)
    searcher = open_searcher(index_dir)
    try:
        print(f"Ready: {len(meta)} documents. BM25 k1={BM25_K1}, b={BM25_B}")
        while True:
            try:
                query = input("\nSearch (or 'exit'): ").strip()
            except EOFError:
                break
            if query.lower() == "exit":
                break
            if not query:
                continue

            results = _format_hits(meta, search_hits(searcher, query, TOP_K))
            if not results:
                print("No results.")
                continue
            for rank, result in enumerate(results, 1):
                print(f"\n{rank:2d}. {result['name']}   [id={result['id']}  score={result['score']:.3f}]")
                print(f"    {result['address']}   ({result['lat']}, {result['lon']})")
                print(f"    {result['snippet']}...")
    finally:
        searcher.close()


if __name__ == "__main__":
    main()
