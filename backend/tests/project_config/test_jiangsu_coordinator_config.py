from pathlib import Path

from app.project_config.loader import load_project_context


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_jiangsu_coordinator_uses_project_station_image():
    context = load_project_context("jiangsu-ops", repo_root=REPO_ROOT)

    assert context.manifest.frontend.coordinator is not None
    assert context.manifest.frontend.coordinator.name == "苏小环"
    assert (
        context.manifest.frontend.coordinator.station_image_url
        == "/project-assets/jiangsu-ops/nanjing-demo-station.png"
    )
    assert (
        REPO_ROOT
        / "frontend/public/project-assets/jiangsu-ops/nanjing-demo-station.png"
    ).is_file()
