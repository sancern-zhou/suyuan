import json
import subprocess
import sys


def test_cli_creates_point_layer_program():
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.tools.gisctl.cli",
            "map-spec",
            "create",
            "point-layer",
            "--data-id",
            "air_quality_station_hour:v1:abc123",
            "--layer-id",
            "turn_12_pm25_high",
            "--name",
            "PM2.5 high stations",
            "--lon",
            "longitude",
            "--lat",
            "latitude",
            "--color-by",
            "pm25",
            "--breaks",
            "35,75,115",
            "--colors",
            "#facc15,#fb923c,#ef4444",
        ],
        cwd="backend",
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["success"] is True
    assert payload["status"] == "success"
    assert payload["metadata"]["map_program"]["state"]["layers"][0]["id"] == "turn_12_pm25_high"


def test_cli_creates_set_view_program():
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.tools.gisctl.cli",
            "map-spec",
            "create",
            "set-view",
            "--center",
            "113.2644,23.1291",
            "--zoom",
            "10",
            "--name",
            "广州",
        ],
        cwd="backend",
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["success"] is True
    assert payload["status"] == "success"
    assert payload["metadata"]["map_program"]["state"]["view"]["center"] == [113.2644, 23.1291]
    assert payload["metadata"]["map_program"]["state"]["layers"] == []
