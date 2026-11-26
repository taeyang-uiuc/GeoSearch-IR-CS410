"""
bm25_search.py
Build a Pyserini BM25 index from restaurants.jsonl (fields: id, contents, name, address, lat, lon)
and search it interactively.

Usage:
    conda activate pyserini
    python bm25_search.py                       # uses restaurants.jsonl
    python bm25_search.py path/to/file.jsonl    # custom input
    python bm25_search.py --rebuild             # force re-indexing
"""
import os
import sys
import json
import shutil
import subprocess

# pyserini builds an OpenAI client at import time; a dummy key avoids the error
os.environ.setdefault("OPENAI_API_KEY", "dummy")
os.environ["JAVA_HOME"] = "/opt/anaconda3/envs/pyserini/lib/jvm"
os.environ["JVM_PATH"] = "/opt/anaconda3/envs/pyserini/lib/jvm/lib/server/libjvm.dylib"

from pyserini.search.lucene import LuceneSearcher
from jnius import autoclass

# ---------------- settings ----------------
BASE_DIR   = "/Users/swsanyal/codebases/GeoSearch-IR-CS410"
INPUT_FILE = os.path.join(BASE_DIR, "data", "restaurants.jsonl")
WORK_DIR   = os.path.join(BASE_DIR, "geosearch_work")
TOP_K = 10
BM25_K1, BM25_B = 0.9, 0.4
SNIPPET_CHARS = 160
# ------------------------------------------


def clean_text(text):
    """The reviews contain literal backslash-n sequences; turn them into spaces."""
    return " ".join(str(text).replace("\\n", " ").split())


def build_index(input_file):
    """Write a cleaned JsonCollection (id + contents) and run the Lucene indexer."""
    docs_dir = os.path.join(WORK_DIR, "docs")
    index_dir = os.path.join(WORK_DIR, "index")
    shutil.rmtree(WORK_DIR, ignore_errors=True)
    os.makedirs(docs_dir)

    n = 0
    with open(input_file, encoding="utf-8") as f, \
         open(os.path.join(docs_dir, "docs.jsonl"), "w", encoding="utf-8") as out:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            contents = clean_text(rec.get("contents", ""))
            if not contents:
                continue
            out.write(json.dumps({"id": str(rec["id"]), "contents": contents}) + "\n")
            n += 1

    print(f"Indexing {n} documents ...")
    run = subprocess.run(
        [sys.executable, "-m", "pyserini.index.lucene",
         "--collection", "JsonCollection",
         "--input", docs_dir,
         "--index", index_dir,
         "--generator", "DefaultLuceneDocumentGenerator",
         "--threads", "1",
         "--storePositions", "--storeDocvectors", "--storeRaw"],
        capture_output=True, text=True)
    if run.returncode != 0:
        raise RuntimeError("Indexing failed:\n" + (run.stderr or run.stdout)[-2000:])
    print("Index built at", index_dir)
    return index_dir


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


def bm25_search(
    meta: dict,
    index_dir: str,
    query: str,
    top_k: int = TOP_K,
    allowed_ids: set | None = None,
) -> list[dict]:
    """Search the Lucene index and return ranked results.

    Args:
        meta:        id -> {name, address, lat, lon, contents} from load_metadata()
        index_dir:   path to the Lucene index directory
        query:       search query string
        top_k:       number of results to return
        allowed_ids: optional set of doc IDs to restrict search to

    Returns:
        List of dicts with keys: id, score, name, address, lat, lon, snippet
    """
    searcher = LuceneSearcher(index_dir)
    searcher.set_bm25(k1=BM25_K1, b=BM25_B)

    if allowed_ids is not None:
        BooleanQuery = autoclass("org.apache.lucene.search.BooleanQuery$Builder")
        TermInSetQuery = autoclass("org.apache.lucene.search.TermInSetQuery")
        Occur = autoclass("org.apache.lucene.search.BooleanClause$Occur")
        BytesRef = autoclass("org.apache.lucene.util.BytesRef")
        QueryParser = autoclass("org.apache.lucene.queryparser.classic.QueryParser")

        ArrayList = autoclass("java.util.ArrayList")
        bytes_list = ArrayList()
        for docid in allowed_ids:
            bytes_list.add(BytesRef(docid.encode()))
        docid_filter = TermInSetQuery("id", bytes_list)

        parser = QueryParser("contents", searcher.object.analyzer)
        bm25_query = parser.parse(QueryParser.escape(query))

        builder = BooleanQuery()
        builder.add(bm25_query, Occur.MUST)
        builder.add(docid_filter, Occur.FILTER)
        raw_hits = searcher.object.search(builder.build(), top_k)
    else:
        raw_hits = searcher.search(query, top_k)

    results = []
    for h in raw_hits:
        m = meta.get(h.docid, {})
        results.append({
            "id": h.docid,
            "score": h.score,
            "name": m.get("name", ""),
            "address": m.get("address", ""),
            "lat": m.get("lat"),
            "lon": m.get("lon"),
            "snippet": m.get("contents", "")[:SNIPPET_CHARS],
        })
    return results


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    input_file = args[0] if args else INPUT_FILE
    rebuild = "--rebuild" in sys.argv

    index_dir = os.path.join(WORK_DIR, "index")
    if rebuild or not os.path.isdir(index_dir):
        build_index(input_file)
    else:
        print(f"Using existing index at {index_dir} (use --rebuild to re-index).")

    meta = load_metadata(input_file)
    print(f"Ready: {len(meta)} documents. BM25 k1={BM25_K1}, b={BM25_B}")

    while True:
        query = input("\nSearch (or 'exit'): ").strip()
        if query.lower() == "exit":
            break
        if not query:
            continue

        nearby_ids = {"G58YATMKnn-M-RUDWg3lxw", "vPTkG6k_ZzLakPp4s-gQJQ"}
        results = bm25_search(meta, index_dir, query, allowed_ids=nearby_ids)
        if not results:
            print("No results.")
            continue
        for rank, r in enumerate(results, 1):
            print(f"\n{rank:2d}. {r['name']}   [id={r['id']}  score={r['score']:.3f}]")
            print(f"    {r['address']}   ({r['lat']}, {r['lon']})")
            print(f"    {r['snippet']}...")


if __name__ == "__main__":
    main()
