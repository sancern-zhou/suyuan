from __future__ import annotations

import argparse

from app.services.pollution_source_asset import register_pollution_source_excel


def main() -> None:
    parser = argparse.ArgumentParser(description="Register pollution source Excel as a DataRegistry point asset.")
    parser.add_argument("excel_path", help="Path to the pollution source Excel file.")
    parser.add_argument("--sheet", default="Sheet1", help="Excel sheet name. Defaults to Sheet1.")
    parser.add_argument(
        "--data-id",
        default="pollution_source_asset:v1:guangdong_emission_inventory_29a8f794",
        help="Stable DataRegistry data_id for the asset.",
    )
    args = parser.parse_args()

    result = register_pollution_source_excel(
        args.excel_path,
        sheet_name=args.sheet,
        data_id=args.data_id,
    )
    print(
        {
            "data_id": result.data_id,
            "record_count": result.record_count,
            "invalid_coordinate_count": result.invalid_coordinate_count,
        }
    )


if __name__ == "__main__":
    main()
