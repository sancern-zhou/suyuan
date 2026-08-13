from app.tools.analysis.calculate_vocs_pmf.tool import CalculateVOCSPMFTool


def test_flat_vocs_records_are_accepted_for_pmf_input():
    tool = CalculateVOCSPMFTool()

    transformed = tool._transform_vocs_to_pmf_input(
        [
            {
                "timestamp": "2026-06-01 00:00:00",
                "station_code": "1006b",
                "station_name": "公园前",
                "data_type": 0,
                "time_type": 1,
            },
            {
                "timestamp": "2026-06-01 01:00:00",
                "station_code": "1006b",
                "station_name": "公园前",
                "data_type": 0,
                "time_type": 1,
                "tvoc": 174.799,
                "alkanes": 43.655,
                "alkenes": 13.422,
                "alkynes": 0.0,
                "aromatics": 35.643,
                "ovocs": 29.782,
                "halogenated": 50.83,
                "organic_sulfur": 1.467,
            }
        ]
    )

    assert transformed == [
        {
            "time": "2026-06-01 01:00:00",
            "alkanes": 43.655,
            "alkenes": 13.422,
            "alkynes": 0.0,
            "aromatics": 35.643,
            "ovocs": 29.782,
            "halogenated": 50.83,
            "organic_sulfur": 1.467,
        }
    ]
