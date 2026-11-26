import ast
import json
import math
import pandas as pd

# Scalar keys to extract from the attributes dict (nested dicts skipped)
SCALAR_ATTRS = [
    "RestaurantsGoodForGroups", "RestaurantsTakeOut", "RestaurantsPriceRange2",
    "GoodForKids", "RestaurantsReservations", "RestaurantsDelivery",
    "RestaurantsAttire", "OutdoorSeating", "HasTV", "Alcohol", "NoiseLevel",
    "WiFi", "BikeParking", "Caters", "BusinessAcceptsCreditCards",
    "RestaurantsTableService", "WheelchairAccessible", "HappyHour",
    "GoodForDancing", "DogsAllowed", "Smoking",
]

LOAD_COLS = [
    "business_id", "name", "latitude", "longitude",
    "address", "city", "state", "postal_code",
    "stars", "review_count", "is_open", "label", "attributes",
]


def _clean(v):
    if isinstance(v, float) and math.isnan(v):
        return None
    if hasattr(v, 'item'):
        v = v.item()
    return v


def _parse_attrs(raw):
    """Parse the attributes string and return a flat dict of scalar values."""
    if not isinstance(raw, str):
        return {}
    try:
        d = ast.literal_eval(raw)
    except Exception:
        return {}
    if not isinstance(d, dict):
        return {}
    out = {}
    for key in SCALAR_ATTRS:
        if key not in d:
            continue
        val = d[key]
        # Strip wrapping quotes from strings like "'no'"
        if isinstance(val, str):
            val = val.strip()
            if val.startswith("'") and val.endswith("'"):
                val = val[1:-1]
        # Coerce bool strings
        if val == 'True':
            val = True
        elif val == 'False':
            val = False
        out[key] = val
    return out


def csv_to_geojson(csv_path: str, geojson_path: str) -> None:
    df = pd.read_csv(csv_path, usecols=LOAD_COLS)
    df = df.dropna(subset=["latitude", "longitude"])
    for col in ["address", "name", "city", "state", "business_id", "label"]:
        df[col] = df[col].fillna("").astype(str)

    features = []
    for row in df.itertuples():
        attrs = _parse_attrs(row.attributes)
        props = {
            "business_id":  row.business_id,
            "name":         row.name,
            "address":      row.address,
            "city":         row.city,
            "state":        row.state,
            "postal_code":  _clean(row.postal_code),
            "stars":        _clean(row.stars),
            "review_count": _clean(row.review_count),
            "is_open":      _clean(row.is_open),
            "label":        row.label,
        }
        props.update(attrs)
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [row.longitude, row.latitude]},
            "properties": props,
        })

    geojson = {"type": "FeatureCollection", "features": features}

    with open(geojson_path, "w") as f:
        json.dump(geojson, f, indent=2, allow_nan=False)

    print(f"Wrote {len(features)} features to {geojson_path}")


if __name__ == "__main__":
    csv_to_geojson(
        csv_path="src/resources/restaurant_reviews.csv",
        geojson_path="src/resources/restaurant_reviews.geojson",
    )
