"""重生成采集库（DataCrawler MySQL）表契约 data_table_contracts.yaml。

在既有类别分组（time/dimension/value/mark/caliber_columns）基础上补充
column_types（来自 information_schema.columns 的精确类型），供
data_shape 输出精确元数据。需在能连接采集库的环境执行：

    cd backend && python scripts/generate_data_table_contracts.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.tools.query.execute_crawler_sql_query.table_contracts import (  # noqa: E402
    CONTRACT_FILENAME,
    load_table_contracts,
)
from app.utils.path_config import PROJECT_ROOT  # noqa: E402


def main() -> int:
    import structlog

    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(30))
    from config.settings import settings
    from sqlalchemy import create_engine, text

    contracts_path = Path(settings.data_registry_dir) / CONTRACT_FILENAME
    if not contracts_path.exists():
        contracts_path = PROJECT_ROOT / "backend" / "config" / CONTRACT_FILENAME

    contracts = load_table_contracts(refresh=True)
    if not contracts:
        print("contracts unavailable")
        return 1
    tables = contracts["tables"]

    engine = create_engine(settings.crawler_mysql_url.replace("+aiomysql", "+pymysql"))
    with engine.connect() as connection:
        rows = connection.execute(text(
            "SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE FROM information_schema.columns "
            "WHERE TABLE_SCHEMA = DATABASE() ORDER BY TABLE_NAME, ORDINAL_POSITION"
        )).mappings().all()

    types_by_table: dict[str, dict[str, str]] = {}
    for row in rows:
        types_by_table.setdefault(str(row["TABLE_NAME"]), {})[
            str(row["COLUMN_NAME"])
        ] = str(row["DATA_TYPE"])

    missing_columns = []
    for table_name, info in tables.items():
        column_types = types_by_table.get(table_name, {})
        if not column_types:
            print(f"WARNING: no information_schema rows for {table_name}")
        known = set(column_types)
        for key in ("time_columns", "dimension_columns", "value_columns", "mark_columns", "caliber_columns"):
            for column in info.get(key) or []:
                if known and column not in known:
                    missing_columns.append(f"{table_name}.{column}")
        info["column_types"] = column_types

    payload = {"tables": tables}
    contracts_path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=200),
        encoding="utf-8",
    )
    print(f"written: {contracts_path}")
    print(f"tables: {len(tables)}, columns typed: {sum(len(v) for v in types_by_table.values())}")
    if missing_columns:
        print(f"columns missing from information_schema ({len(missing_columns)}):")
        for item in missing_columns[:20]:
            print(f"  - {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
