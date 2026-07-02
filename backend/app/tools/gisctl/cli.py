from __future__ import annotations

import argparse
import json
from typing import Sequence

from app.tools.gisctl.map_spec import create_point_layer_program, create_set_view_program
from app.tools.gisctl.models import GisctlResult


def _parse_csv_floats(value: str) -> list[float]:
    return [float(item.strip()) for item in value.split(",") if item.strip()]


def _parse_csv_strings(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_center(value: str) -> list[float]:
    parts = _parse_csv_floats(value)
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("center must be 'longitude,latitude'")
    return parts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gisctl")
    sub = parser.add_subparsers(dest="family", required=True)

    map_spec = sub.add_parser("map-spec")
    map_spec_sub = map_spec.add_subparsers(dest="action", required=True)
    create = map_spec_sub.add_parser("create")
    create_sub = create.add_subparsers(dest="kind", required=True)
    point = create_sub.add_parser("point-layer")
    point.add_argument("--data-id", required=True)
    point.add_argument("--layer-id", required=True)
    point.add_argument("--name", required=True)
    point.add_argument("--lon", required=True)
    point.add_argument("--lat", required=True)
    point.add_argument("--color-by")
    point.add_argument("--breaks", default="")
    point.add_argument("--colors", default="")

    set_view = create_sub.add_parser("set-view")
    set_view.add_argument("--center", required=True, type=_parse_center)
    set_view.add_argument("--zoom", type=float)
    set_view.add_argument("--name", required=True)
    return parser


def run(argv: Sequence[str] | None = None) -> GisctlResult:
    args = build_parser().parse_args(argv)
    if args.family == "map-spec" and args.action == "create" and args.kind == "point-layer":
        program = create_point_layer_program(
            data_id=args.data_id,
            layer_id=args.layer_id,
            name=args.name,
            longitude_field=args.lon,
            latitude_field=args.lat,
            color_by=args.color_by,
            breaks=_parse_csv_floats(args.breaks) if args.breaks else None,
            colors=_parse_csv_strings(args.colors) if args.colors else None,
        )
        return GisctlResult.from_map_program(
            command="map-spec create point-layer",
            data_ids=[args.data_id],
            map_program=program.model_dump(),
            summary=f"Created point layer map program {args.layer_id}",
        )
    if args.family == "map-spec" and args.action == "create" and args.kind == "set-view":
        program = create_set_view_program(
            center=args.center,
            zoom=args.zoom,
            name=args.name,
        )
        return GisctlResult.from_map_program(
            command="map-spec create set-view",
            data_ids=[],
            map_program=program.model_dump(),
            summary=f"Created set-view map program {args.name}",
        )
    raise SystemExit("Unsupported gisctl command")


def main(argv: Sequence[str] | None = None) -> None:
    result = run(argv)
    print(json.dumps(result.model_dump(), ensure_ascii=False))


if __name__ == "__main__":
    main()
