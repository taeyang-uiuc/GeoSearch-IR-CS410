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
# If Java is not found, uncomment and set JAVA_HOME (and JVM_PATH) before the import below:
os.environ["JAVA_HOME"] = "/opt/miniconda3/envs/pyserini/lib/jvm"
os.environ["JVM_PATH"] = "/opt/miniconda3/envs/pyserini/lib/server/libjvm.dylib"

from pyserini.search.lucene import LuceneSearcher

# ---------------- settings ----------------
INPUT_FILE = "restaurants.jsonl"
WORK_DIR = "geosearch_work"

BASE_DIR   = "/Users/sumanmookherjee/Downloads/Masters in CS/Text Information Systems/GeoSearch-IR-CS410"
INPUT_FILE = os.path.join(BASE_DIR, "data", "restaurants.jsonl")
WORK_DIR   = os.path.join(BASE_DIR, "geosearch_work")
TOP_K = 10
BM25_K1, BM25_B = 0.9, 0.4          # Pyserini defaults; tune with your evaluation queries
SNIPPET_CHARS = 160
# ------------------------------------------


def clean_text(text):
    """The reviews contain literal backslash-n sequences; turn them into spaces."""
    return " ".join(str(text).replace("\\n", " ").split())


def build_index(input_file):
    """Write a cleaned JsonCollection (id + contents) and run the Lucene indexer.
    Returns the index directory and a dict id -> record (kept for display, lat/lon, etc.)."""
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
                continue                                   # nothing to index
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
    searcher = LuceneSearcher(index_dir)
    searcher.set_bm25(k1=BM25_K1, b=BM25_B)
    print(f"Ready: {searcher.num_docs} documents. BM25 k1={BM25_K1}, b={BM25_B}")

    while True:
        query = input("\nSearch (or 'exit'): ").strip()
        if query.lower() == "exit":
            break
        if not query:
            continue
        hits = searcher.search(query, TOP_K)
        if not hits:
            print("No results.")
            continue
        for rank, h in enumerate(hits, 1):
            m = meta.get(h.docid, {})
            print(f"\n{rank:2d}. {m.get('name', '?')}   [id={h.docid}  score={h.score:.3f}]")
            print(f"    {m.get('address', '')}   ({m.get('lat')}, {m.get('lon')})")
            print(f"    {m.get('contents', '')[:SNIPPET_CHARS]}...")


if __name__ == "__main__":
    main()
