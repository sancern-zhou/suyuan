from app.scenarios.xuchang_transport_escalation.cwt_analysis import calculate_wcwt


def _samples(count: int) -> list[dict]:
    samples = []
    for sample_index in range(count):
        endpoints = []
        for trajectory_id, height in ((1, 100), (2, 500), (3, 1000)):
            for age in range(49):
                endpoints.append(
                    {
                        "trajectory_id": trajectory_id,
                        "age_hours": -age,
                        "lat": 34.03 + age * 0.006 + trajectory_id * 0.002,
                        "lon": 113.85 - age * 0.012 + sample_index * 0.0002,
                        "height": height,
                    }
                )
        samples.append(
            {
                "arrival_time": f"2026-01-{sample_index // 24 + 1:02d}T{sample_index % 24:02d}:00:00+08:00",
                "sample_group": "pollution" if sample_index % 2 else "control",
                "concentration": 40.0 + sample_index,
                "endpoints": endpoints,
            }
        )
    return samples


def test_wcwt_waits_for_minimum_sample_count():
    result = calculate_wcwt(
        _samples(29),
        heights_m_agl=[100, 500, 1000],
        backtrack_hours=48,
    )

    assert result["status"] == "accumulating_samples"
    assert result["heights"]["100"]["valid_trajectory_count"] == 29
    assert result["heights"]["100"]["cells"] == []


def test_wcwt_calculates_residence_weighted_grids_by_height():
    result = calculate_wcwt(
        _samples(30),
        heights_m_agl=[100, 500, 1000],
        backtrack_hours=48,
    )

    assert result["status"] == "completed"
    assert set(result["heights"]) == {"100", "500", "1000"}
    for height in result["heights"].values():
        assert height["valid_trajectory_count"] == 30
        assert height["occupied_grid_count"] > 0
        assert height["cells"]
        assert height["high_value_cells"]
        assert all(cell["residence_hours"] > 0 for cell in height["cells"])
        assert all(0 < cell["sample_weight"] <= 1 for cell in height["cells"])
