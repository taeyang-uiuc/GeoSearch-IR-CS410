import json
import pandas as pd


def csv_to_geojson(csv_path: str, geojson_path: str) -> None:
    df = pd.read_csv(csv_path, usecols=["business_id", "name", "latitude", "longitude", "address", "city", "state"])
    df = df.dropna(subset=["latitude", "longitude"])

    features = [
        {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [row.longitude, row.latitude],
            },
            "properties": {
                "business_id": row.business_id,
                "name": row.name,
                "address": row.address,
                "city": row.city,
                "state": row.state,
            },
        }
        for row in df.itertuples()
    ]

    geojson = {"type": "FeatureCollection", "features": features}

    with open(geojson_path, "w") as f:
        json.dump(geojson, f, indent=2)

    print(f"Wrote {len(features)} features to {geojson_path}")


if __name__ == "__main__":
    csv_to_geojson(
        csv_path="src/resources/restaurant_reviews.csv",
        geojson_path="src/resources/restaurant_reviews.geojson",
    )
