"""Render stored alert evidence without publishing events or sending messages.

Run from any directory with backend_py311 Python; all paths are project-relative.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Bootstrap import only; all user paths below use the shared path contract.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.utils.path_config import resolve_agent_path, get_data_registry, format_agent_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", help="Stored episode evidence; defaults to latest")
    parser.add_argument("--env-file", default="backend/.env")
    parser.add_argument("--output-dir", help="Defaults to data registry/road_dispatch_preview")
    args = parser.parse_args()
    from dotenv import load_dotenv
    load_dotenv(resolve_agent_path(args.env_file), override=False)
    from app.scenarios.xuchang_station_deviation.dispatch import UpwindRoadDispatchBuilder
    source = resolve_agent_path(args.evidence) if args.evidence else max(
        (get_data_registry()/"xuchang_station_deviation_alerts").glob("*/*.evidence.json"),
        key=lambda p: p.stat().st_mtime)
    payload = json.loads(source.read_text(encoding="utf-8"))
    output = resolve_agent_path(args.output_dir) if args.output_dir else get_data_registry()/"road_dispatch_preview"
    builder = UpwindRoadDispatchBuilder(output_root=output)
    items = payload.get("alerts") or [{"alert": payload["event"], "evidence": payload}]
    scopes = {}
    previews = []
    for item in items:
        alert, evidence = item["alert"], item["evidence"]
        key = (alert["station_id"], alert["occurred_at"])
        if key not in scopes:
            scopes[key] = builder.build(alert, evidence)
        scope = scopes[key]
        previews.append({"event_id": alert["event_id"], "station_name": alert["station_name"],
                         "upwind_road_scope": scope, "dispatch_guidance": builder.guidance(alert, scope)})
    result = {"source_evidence": format_agent_path(source), "preview_only": True, "alerts": previews}
    builder._write_json(output/"preview.json", result)
    print(json.dumps({"preview_path": format_agent_path(output/"preview.json"), "alerts": [
        {"station": p["station_name"], "status": p["upwind_road_scope"]["status"],
         "map_status": p["upwind_road_scope"]["map_status"],
         "roads": p["dispatch_guidance"]["road_names"],
         "image": p["upwind_road_scope"].get("upwind_road_scope_image_path"),
         "errors": p["upwind_road_scope"]["errors"]} for p in previews]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
