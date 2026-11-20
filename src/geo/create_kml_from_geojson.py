import json
import simplekml


def geojson_to_kml(geojson_path: str, kml_path: str) -> None:
    with open(geojson_path) as f:
        geojson = json.load(f)

    kml = simplekml.Kml()

    for feature in geojson["features"]:
        lon, lat = feature["geometry"]["coordinates"]
        props = feature["properties"]

        point = kml.newpoint(
            name=str(props.get("name", "")),
            coords=[(lon, lat, 10)],
        )
        point.description = "".join(f"<b>{k}</b>: {v}<br/>" for k, v in props.items())
        point.altitudemode = simplekml.AltitudeMode.relativetoground
        point.extrude = 1

    kml.save(kml_path)
    print(f"Wrote {len(geojson['features'])} placemarks to {kml_path}")


if __name__ == "__main__":
    geojson_to_kml(
        geojson_path="src/resources/restaurant_reviews.geojson",
        kml_path="src/resources/restaurant_reviews.kml",
    )
