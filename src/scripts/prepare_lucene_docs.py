"""
Reads restaurant_reviews.csv and writes a .jsonl file for Pyserini/Lucene indexing.
Each line is one JSON doc with `contents` (BM25-indexed) and stored fields.

Usage:
    python src/scripts/prepare_lucene_docs.py \
        --input src/resources \
        --output src/resources/lucene_docs
"""

import argparse
import ast
import json
import os
import pandas as pd


PRICE_MAP = {"1": "low", "2": "medium", "3": "high", "4": "very high"}


def parse_attributes(raw):
    try:
        return ast.literal_eval(raw)
    except Exception:
        return {}


def extract_attr(attrs, key, default=None):
    val = attrs.get(key, default)
    if val is None:
        return default
    # strip surrounding quotes from string values like "'loud'"
    if isinstance(val, str):
        val = val.strip().strip("'\"")
    return val


def bool_to_str(val):
    if isinstance(val, bool):
        return "yes" if val else "no"
    if isinstance(val, str):
        return "yes" if val.strip().lower() == "true" else "no"
    return "no"


def build_contents(row, attrs):
    price = PRICE_MAP.get(str(extract_attr(attrs, "RestaurantsPriceRange2", "")).strip(), "unknown")
    noise = extract_attr(attrs, "NoiseLevel", "unknown")
    outdoor = bool_to_str(extract_attr(attrs, "OutdoorSeating", False))
    groups = bool_to_str(extract_attr(attrs, "RestaurantsGoodForGroups", False))
    kids = bool_to_str(extract_attr(attrs, "GoodForKids", False))
    takeout = bool_to_str(extract_attr(attrs, "RestaurantsTakeOut", False))
    reservations = bool_to_str(extract_attr(attrs, "RestaurantsReservations", False))

    ambience_raw = extract_attr(attrs, "Ambience", {})
    if isinstance(ambience_raw, str):
        try:
            ambience_raw = ast.literal_eval(ambience_raw)
        except Exception:
            ambience_raw = {}
    ambience_tags = [k for k, v in ambience_raw.items() if str(v).strip().lower() == "true"] if isinstance(ambience_raw, dict) else []
    ambience_str = ", ".join(ambience_tags) if ambience_tags else "casual"

    parking_raw = extract_attr(attrs, "BusinessParking", {})
    if isinstance(parking_raw, str):
        try:
            parking_raw = ast.literal_eval(parking_raw)
        except Exception:
            parking_raw = {}
    valet = bool_to_str(parking_raw.get("valet", False) if isinstance(parking_raw, dict) else False)

    parts = [
        f"{row['label']} restaurant in {row['city']}.",
        f"price: {price}.",
        f"noise: {noise}.",
        f"outdoor seating: {outdoor}.",
        f"good for groups: {groups}.",
        f"good for kids: {kids}.",
        f"takeout: {takeout}.",
        f"reservations: {reservations}.",
        f"valet parking: {valet}.",
        f"ambience: {ambience_str}.",
        f"stars: {row['stars']}.",
        f"reviews: {row['review']}",
    ]
    return " ".join(parts)


def prepare(input_dir, output_dir):
    csv_path = os.path.join(input_dir, "restaurant_reviews.csv")
    df = pd.read_csv(csv_path)

    # drop rows missing coordinates or business_id
    df = df.dropna(subset=["latitude", "longitude", "business_id"])
    df = df[df["latitude"] != 0]

    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, "restaurants.jsonl")

    written = 0
    with open(out_path, "w", encoding="utf-8") as f:
        for _, row in df.iterrows():
            attrs = parse_attributes(row.get("attributes", "{}"))
            doc = {
                "id": row["business_id"],
                "contents": build_contents(row, attrs),
                "name": row["name"],
                "address": f"{row['address']}, {row['city']}, {row['state']}",
                "lat": row["latitude"],
                "lon": row["longitude"],
            }
            f.write(json.dumps(doc, ensure_ascii=False) + "\n")
            written += 1

    print(f"Written {written} docs to {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Directory containing restaurant_reviews.csv")
    parser.add_argument("--output", required=True, help="Output directory for .jsonl file")
    args = parser.parse_args()
    prepare(args.input, args.output)
