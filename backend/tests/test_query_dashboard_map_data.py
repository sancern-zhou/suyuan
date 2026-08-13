from app.services.query_dashboard_map_data import dataset_to_geojson_features


def test_dataset_to_geojson_features_uses_lon_lat_fields():
    dataset = [
        {"station_name": "A", "longitude": 113.26, "latitude": 23.13, "pm25": 88},
        {"station_name": "B", "longitude": None, "latitude": 23.2, "pm25": 60},
    ]

    features = dataset_to_geojson_features(
        dataset,
        longitude_field="longitude",
        latitude_field="latitude",
    )

    assert features == [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [113.26, 23.13]},
            "properties": {"station_name": "A", "pm25": 88},
        }
    ]


def test_dataset_to_geojson_features_reads_named_view():
    dataset = {
        "views": {
            "stations": [
                {"name": "A", "lon": "113.26", "lat": "23.13"},
            ]
        }
    }

    features = dataset_to_geojson_features(
        dataset,
        longitude_field="lon",
        latitude_field="lat",
        view="stations",
    )

    assert features[0]["geometry"]["coordinates"] == [113.26, 23.13]
    assert features[0]["properties"] == {"name": "A"}


def test_dataset_to_geojson_features_uses_existing_geometry_field():
    geometry = {
        "type": "Polygon",
        "coordinates": [[
            [113.2, 23.1],
            [113.3, 23.1],
            [113.3, 23.2],
            [113.2, 23.1],
        ]],
    }
    dataset = [
        {
            "name": "花都师范 3km 缓冲区",
            "geometry": geometry,
            "buffer_distance_m": 3000,
        }
    ]

    features = dataset_to_geojson_features(
        dataset,
        longitude_field="longitude",
        latitude_field="latitude",
    )

    assert features == [
        {
            "type": "Feature",
            "geometry": geometry,
            "properties": {
                "name": "花都师范 3km 缓冲区",
                "buffer_distance_m": 3000,
            },
        }
    ]
