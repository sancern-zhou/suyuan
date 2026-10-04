"""数据形状（data_shape）：外置数据文件的列名/类型/行数元数据。

数据查询工具与 execute_python 保存产物时生成，随工具结果返回 LLM 上下文，
并写入资源元数据随 DAG 资源交接流转，避免下游模型凭记忆猜测列名。
"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

# 形状行渲染时最多展示的列数，超出部分以“…共 N 列”收尾
MAX_SHAPE_COLUMNS = 12

_DATE_TYPES = {"date", "datetime", "timestamp", "datetime64", "DATETIME", "DATE", "TIMESTAMP"}


def _type_of_value(value: Any) -> str:
    if value is None or isinstance(value, str):
        return "str"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    return "str"


def infer_column_types(
    records: Sequence[Mapping[str, Any]],
    columns: Optional[Sequence[str]] = None,
) -> dict[str, str]:
    """从样本记录推断列类型（仅用于无法获得库侧精确类型的派生列）。"""
    names = list(columns) if columns else list(records[0].keys() if records else [])
    types: dict[str, str] = {}
    for name in names:
        inferred = "str"
        for record in records[:20]:
            value = record.get(name)
            if value is None:
                continue
            inferred = _type_of_value(value)
            break
        types[str(name)] = inferred
    return types


def build_data_shape(
    columns_with_types: Mapping[str, str],
    row_count: int,
    source: str,
) -> dict[str, Any]:
    """构造 data_shape 元数据块。

    columns_with_types: 列名 -> 读回类型（库侧精确类型优先，派生列标 inferred）。
    source: 类型来源，db / information_schema / dataframe / inferred。
    """
    columns = [
        {"name": str(name), "type": str(dtype)}
        for name, dtype in columns_with_types.items()
    ]
    return {
        "columns": columns,
        "row_count": int(row_count),
        "source": str(source),
    }


def shape_from_records(
    records: Sequence[Mapping[str, Any]],
    row_count: int,
    source: str = "inferred",
) -> dict[str, Any]:
    """无库侧类型时的便捷构造：全部列由样本推断。"""
    return build_data_shape(infer_column_types(records), row_count, source)


def render_shape_line(shape: Mapping[str, Any], max_columns: int = MAX_SHAPE_COLUMNS) -> str:
    """渲染为紧凑单行：`列A:str, 列B:float | 864行`；无列时仅返回行数（如 `0行`）。

    兼容 stdout 截断产物：`columns_total` 记录真实总列数，截断展示时以它收尾。
    """
    columns = shape.get("columns") or []
    row_count = shape.get("row_count")
    parts = [f"{item.get('name')}:{item.get('type')}" for item in columns[:max_columns]]
    total = shape.get("columns_total")
    if not isinstance(total, int) or total <= 0:
        total = len(columns)
    if total > max_columns:
        parts.append(f"…共 {total} 列")
    line = ", ".join(parts)
    if row_count is not None:
        line = f"{line} | {row_count}行" if line else f"{row_count}行"
    return line


def shape_summary_suffix(shape: Optional[Mapping[str, Any]]) -> str:
    """工具 summary 末尾追加的形状提示；无形状时返回空串。"""
    if not shape:
        return ""
    line = render_shape_line(shape)
    if not line:
        return ""
    return f"数据形状：{line}"


def dataframe_column_types(dataframe: Any) -> dict[str, str]:
    """从 pandas DataFrame 提取“读回后”的列类型（datetime 列读回为 ISO 字符串）。"""
    types: dict[str, str] = {}
    for name in getattr(dataframe, "columns", []):
        dtype = str(dataframe[name].dtype)
        if dtype.startswith("datetime"):
            types[str(name)] = "datetime-str"
        elif dtype in ("int64", "int32"):
            types[str(name)] = "int"
        elif dtype in ("float64", "float32"):
            types[str(name)] = "float"
        elif dtype == "bool":
            types[str(name)] = "bool"
        else:
            types[str(name)] = "str"
    return types


def is_datetime_type(dtype: str) -> bool:
    return str(dtype) in _DATE_TYPES or str(dtype).startswith("datetime")


class TableTypesCache:
    """按表懒加载 information_schema.columns 列类型（进程内缓存）。

    某表首次出现时查一次元数据，之后命中缓存；查询失败按无类型降级。
    列类型一律按 table_schema 收敛（未显式给 schema 时按 current_schema()），
    避免同库跨 schema 同名表互相污染列类型。
    """

    def __init__(self) -> None:
        self._cache: dict[str, dict[str, str]] = {}

    @staticmethod
    def _split_schema(table: str) -> tuple[Optional[str], str]:
        if "." in table:
            schema, _, name = table.rpartition(".")
            return schema, name
        return None, table

    @classmethod
    def _cache_key(cls, table: str) -> str:
        schema, name = cls._split_schema(str(table))
        return f"{schema}.{name}" if schema else name

    def get(self, table: str) -> dict[str, str]:
        return self._cache.get(self._cache_key(table), {})

    async def load(self, engine: Any, table: str, schema: Optional[str] = None) -> dict[str, str]:
        """查询并缓存一张表的列类型；失败返回空 dict（调用方回退推断）。

        schema 未提供时从表名解析（`schema.table`），仍无则按 current_schema() 匹配。
        """
        table = str(table)
        if not schema:
            schema, table = self._split_schema(table)
        cache_key = f"{schema}.{table}" if schema else table
        if cache_key in self._cache:
            return self._cache[cache_key]
        from sqlalchemy import text

        schema_expr = ":table_schema" if schema else "current_schema()"
        query = text(
            "SELECT COLUMN_NAME AS column_name, DATA_TYPE AS data_type "
            "FROM information_schema.columns "
            f"WHERE table_name = :table_name AND table_schema = {schema_expr}"
        )
        params: dict[str, Any] = {"table_name": table}
        if schema:
            params["table_schema"] = schema
        try:
            async with engine.connect() as connection:
                result = await connection.execute(query, params)
                types = {
                    str(row["column_name"]): str(row["data_type"])
                    for row in result.mappings()
                }
        except Exception:
            types = {}
        if types:
            self._cache[cache_key] = types
        return types
