from __future__ import annotations

from app.services.data_registry import DataRegistryService


def test_load_dataset_reloads_metadata_when_index_is_stale(tmp_path):
    reader = DataRegistryService(base_dir=str(tmp_path))
    writer = DataRegistryService(base_dir=str(tmp_path))

    entry = writer.register_dataset(
        schema="map_point_asset",
        version="v1",
        records=[{"station_name": "花都师范", "longitude": 113.2146, "latitude": 23.3917}],
        data_id="map_point_asset:v1:station_huadu_normal",
    )

    assert reader.get_metadata(entry.data_id) is not None
    assert reader.load_dataset(entry.data_id) == [
        {"station_name": "花都师范", "longitude": 113.2146, "latitude": 23.3917}
    ]

