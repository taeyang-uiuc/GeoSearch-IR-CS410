import geopy
import geopy.distance
import pandas as pd
from rtree import index


def build_rtree(csv_path: str) -> tuple[index.Index, pd.DataFrame]:
    df = pd.read_csv(csv_path, usecols=["business_id", "latitude", "longitude"])
    df = df.dropna(subset=["latitude", "longitude"])

    idx = index.Index()
    for pos, row in enumerate(df.itertuples()):
        idx.insert(pos, (row.longitude, row.latitude, row.longitude, row.latitude))

    return idx, df.reset_index(drop=True)


def query_nearby(idx: index.Index, df: pd.DataFrame, lat: float, lon: float, radius_m: float):
    point = geopy.Point(lat, lon)
    d = geopy.distance.geodesic(meters=radius_m)
    min_lat = d.destination(point, bearing=180).latitude
    max_lat = d.destination(point, bearing=0).latitude
    min_lon = d.destination(point, bearing=270).longitude
    max_lon = d.destination(point, bearing=90).longitude

    candidates = list(idx.intersection((min_lon, min_lat, max_lon, max_lat)))
    return df.iloc[candidates]


if __name__ == "__main__":
    idx, df = build_rtree("src/resources/restaurant_reviews.csv")
    print(f"Indexed {len(df)} venues")

    results = query_nearby(idx, df, lat=36.12, lon=-115.17, radius_m=100)
    print(results)
