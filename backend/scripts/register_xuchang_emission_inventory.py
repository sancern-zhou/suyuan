from __future__ import annotations

import argparse

from app.tools.analysis.xuchang_upwind_permit_sources.inventory_asset import (
    XUCHANG_INVENTORY_DATA_ID,
    register_xuchang_emission_inventory,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Register the Xuchang multi-sheet enterprise emission inventory."
    )
    parser.add_argument("excel_path", help="Project-relative or absolute path to the source XLSX.")
    parser.add_argument(
        "--inventory-period",
        default="unknown",
        help="Inventory year or period. Use 'unknown' when the source does not identify it.",
    )
    parser.add_argument("--data-id", default=XUCHANG_INVENTORY_DATA_ID)
    args = parser.parse_args()

    result = register_xuchang_emission_inventory(
        args.excel_path,
        inventory_period=args.inventory_period,
        data_id=args.data_id,
    )
    print(
        {
            "data_id": result.data_id,
            "source_record_count": result.source_record_count,
            "enterprise_count": result.enterprise_count,
            "geocoded_enterprise_count": result.geocoded_enterprise_count,
            "unlocated_enterprise_count": result.unlocated_enterprise_count,
        }
    )


if __name__ == "__main__":
    main()
