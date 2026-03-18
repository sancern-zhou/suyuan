"""
calculate_soluble: 水溶性离子分析（阴阳离子平衡、三元图、SOR/NOR）

支持两种输入格式：
1. DataFrame: 离子字段在顶层（如 SO4, NO3, NH4）
2. 字典列表: UnifiedParticulateData 格式，离子在 components 字段中

Context-Aware V2: 使用 ExecutionContext 管理数据生命周期
"""
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union
import hashlib
import warnings
import structlog
from scipy import stats
from sklearn.linear_model import LinearRegression
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np

from app.utils.ternary_plot import to_ternary_coordinates
from app.utils.oxidation_rates import calculate_sor, calculate_nor
from app.utils.data_standardizer import get_data_standardizer

logger = structlog.get_logger()

if TYPE_CHECKING:
    from app.agent.context import ExecutionContext

from app.tools.visualization.particulate_visualizer import ParticulateVisualizer

# 默认离子分子量与电荷（UDF v2.0 化学式字段名）
DEFAULT_ION_INFO = {
    "SO4": {"molar_mass": 96.06, "charge": -2},       # SO4^2-
    "NO3": {"molar_mass": 62.0049, "charge": -1},     # NO3-
    "NH4": {"molar_mass": 18.038, "charge": +1},     # NH4+
    "K": {"molar_mass": 39.0983, "charge": +1},   # K+
    "Na": {"molar_mass": 22.9898, "charge": +1},      # Na+
    "Ca": {"molar_mass": 40.078, "charge": +2},      # Ca2+
    "Mg": {"molar_mass": 24.305, "charge": +2},    # Mg2+
    "Cl": {"molar_mass": 35.45, "charge": -1},      # Cl-
}


def _hash_dataframe(df: pd.DataFrame) -> str:
    try:
        b = df.to_csv(index=False).encode("utf-8")
        return hashlib.md5(b).hexdigest()
    except Exception:
        return ""


def _extract_ion_columns(records: List[Dict], ion_info: Dict[str, Dict]) -> pd.DataFrame:
    """从 UnifiedParticulateData 格式的记录中提取离子数据到 DataFrame。

    使用全局 DataStandardizer 进行字段映射（PM2.5, NO2, SO2 等字段名变体统一处理）
    数据格式：UnifiedParticulateData（components 嵌套结构）

    Args:
        records: 包含 components 字段的记录列表
        ion_info: 离子信息字典

    Returns:
        包含离子列的 DataFrame
    """
    if not records:
        logger.warning("[_extract_ion_columns] 输入记录列表为空")
        return pd.DataFrame()

    # 使用全局 DataStandardizer 进行字段映射
    standardizer = get_data_standardizer()

    # 调试：记录第一条原始记录的结构
    first_record = records[0]
    if hasattr(first_record, 'model_dump'):
        first_record_dict = first_record.model_dump()
    else:
        first_record_dict = dict(first_record)

    logger.info(
        "[_extract_ion_columns] 原始数据结构分析",
        first_record_keys=list(first_record_dict.keys()),
        has_components='components' in first_record_dict,
        components_type=type(first_record_dict.get('components')).__name__ if 'components' in first_record_dict else None,
        sample_timestamp=first_record_dict.get('timestamp'),
        sample_station_code=first_record_dict.get('station_code'),
        sample_station_name=first_record_dict.get('station_name'),
    )

    # 【关键调试】检查第一条记录的 components 内容
    if 'components' in first_record_dict:
        components = first_record_dict['components']
        if isinstance(components, dict):
            logger.info(
                "[_extract_ion_columns] components 字段内容",
                component_keys=list(components.keys()),
                sample_values={k: v for k, v in list(components.items())[:10]}
            )
            # 检查是否有已知的离子字段
            known_ions = ['SO4', 'NO3', 'NH4', 'Ca', 'Mg', 'K', 'Na', 'Cl']
            found_ions = [k for k in known_ions if k in components]
            logger.info("[_extract_ion_columns] 已知离子字段检查", found_ions=found_ions)
        elif isinstance(components, list):
            logger.info(
                "[_extract_ion_columns] components 字段是列表",
                length=len(components),
                sample=components[:2] if components else None
            )
        else:
            logger.warning(
                "[_extract_ion_columns] components 字段类型异常",
                type=type(components).__name__
            )
    # 【新增调试】如果 components 不存在，检查顶层是否有离子字段
    else:
        logger.info(
            "[_extract_ion_columns] components 不存在，检查顶层字段",
            top_level_keys=list(first_record_dict.keys())[:20]
        )
        known_ions = ['SO4', 'NO3', 'NH4', 'Ca', 'Mg', 'K', 'Na', 'Cl', 'sulfate', 'nitrate', 'ammonium', 'calcium']
        found_ions_top = [k for k in known_ions if k in first_record_dict]
        if found_ions_top:
            logger.info("[_extract_ion_columns] 顶层找到离子字段", found_ions=found_ions_top)

    rows = []
    for idx, record in enumerate(records):
        # Pydantic 模型转字典
        if hasattr(record, 'model_dump'):
            record_dict = record.model_dump()
        else:
            record_dict = dict(record)

        # 【关键修复】检查原始数据是否已经是 UnifiedParticulateData 格式
        # 如果已经有 components 字段且非空，直接使用，跳过 standardize() 二次处理
        original_components = record_dict.get('components', {})
        is_unified_format = isinstance(original_components, dict) and len(original_components) > 0

        if is_unified_format:
            # 原始数据已是标准格式，直接使用
            standardized_record = record_dict.copy()
            if idx == 0:
                logger.info(
                    "[_extract_ion_columns] 检测到标准格式数据，直接使用原始components",
                    component_keys=list(original_components.keys())[:10]
                )
        else:
            # 原始数据不是标准格式，需要标准化
            standardized_record = standardizer.standardize(record_dict)
            if idx == 0:
                logger.info(
                    "[_extract_ion_columns] 非标准格式数据，进行标准化处理",
                    has_components='components' in standardized_record,
                    component_keys=list(standardized_record.get('components', {}).keys()) if 'components' in standardized_record else None
                )

        if idx == 0:
            logger.info(
                "[_extract_ion_columns] 第一条记录处理后",
                keys=list(standardized_record.keys())[:15],
                has_components='components' in standardized_record
            )

        # 提取时间戳
        timestamp = standardized_record.get('timestamp')
        if idx == 0:
            logger.info("[_extract_ion_columns] timestamp提取", timestamp_value=timestamp)

        # 提取 components（标准化后应该在 components 字段中）
        components = standardized_record.get('components', {})
        if idx == 0:
            logger.info(
                "[_extract_ion_columns] components提取",
                is_dict=isinstance(components, dict),
                keys=list(components.keys()) if isinstance(components, dict) else None,
                empty=len(components) == 0 if isinstance(components, dict) else None
            )

        # 构建行数据
        row = {'timestamp': timestamp}
        row.update(components)  # 添加所有离子数据

        if idx == 0:
            logger.info(
                "[_extract_ion_columns] 添加components后的行数据",
                row_keys=list(row.keys()),
                component_count=len(components) if isinstance(components, dict) else 0
            )

        # PM2.5 可能直接在顶层（标准化后字段名为 PM2_5）
        if 'PM2_5' in standardized_record:
            row['PM2.5'] = standardized_record['PM2_5']
        # 处理其他可能的 PM2.5 字段变体（兜底）
        for key in ['PM2.5', 'PM₂.₅', 'pm25']:
            if key in standardized_record and 'PM2.5' not in row:
                row['PM2.5'] = standardized_record[key]
                if idx == 0:
                    logger.info(f"[_extract_ion_columns] 找到PM2.5字段", original_key=key, value=standardized_record[key])
                break

        # NO2/SO2 可能直接在顶层（标准化后字段名为 NO2, SO2）
        if 'NO2' in standardized_record and 'NO2' not in row:
            row['NO2'] = standardized_record['NO2']
            if idx == 0:
                logger.info("[_extract_ion_columns] 找到NO2字段", value=standardized_record['NO2'])
        if 'SO2' in standardized_record and 'SO2' not in row:
            row['SO2'] = standardized_record['SO2']
            if idx == 0:
                logger.info("[_extract_ion_columns] 找到SO2字段", value=standardized_record['SO2'])

        rows.append(row)

    df = pd.DataFrame(rows)

    # 记录最终 DataFrame 的列信息
    logger.info(
        "[_extract_ion_columns] DataFrame 构建完成",
        columns=list(df.columns),
        row_count=len(df),
        ion_columns=[c for c in df.columns if c in ion_info],
        has_pm25='PM2.5' in df.columns,
        pm25_notna=df['PM2.5'].notna().sum() if 'PM2.5' in df.columns else 0,
        has_no2='NO2' in df.columns,
        has_so2='SO2' in df.columns,
        sample_record=rows[0] if rows else None
    )

    # 设置时间戳索引
    if 'timestamp' in df.columns and df['timestamp'].notna().any():
        df = df.set_index('timestamp')

    return df


def calculate_soluble(
    data: Union[pd.DataFrame, List[Dict]],
    data_id: Optional[str] = None,
    analysis_type: str = "full",
    ion_info: Optional[Dict[str, Dict[str, float]]] = None,
) -> Dict[str, Any]:
    """计算水溶性离子分析结果。

    支持两种输入格式：
    1. DataFrame: 离子字段直接在顶层（如 SO4, NO3, NH4）
    2. 字典列表: UnifiedParticulateData 格式，离子在 components 字段中

    Args:
        data: 输入数据（DataFrame 或 包含 components 的记录列表）
        data_id: 原始数据ID
        analysis_type: 分析类型
        ion_info: 离子分子量与电荷信息

    Returns:
        遵循 UDF v2.0 的分析结果
    """
    if data is None:
        raise ValueError("data 参数不能为 None")

    original_data_id = data_id
    ion_info = ion_info or DEFAULT_ION_INFO

    # 统一转换为 DataFrame
    if isinstance(data, list):
        # 字典列表格式（包含 components 字段）
        df = _extract_ion_columns(data, ion_info)
    else:
        # DataFrame 格式
        df = data.copy()

    if df.empty:
        return {
            "status": "failed",
            "success": False,
            "data": None,
            "metadata": {"tool_name": "calculate_soluble", "error": "empty_data"},
            "summary": "[FAIL] 数据为空"
        }

    # 确保索引名称正确
    if df.index.name is None:
        df.index.name = "timestamp"

    # 1) 电荷量计算
    charge_df = pd.DataFrame(index=df.index)
    for ion, info in ion_info.items():
        if ion in df.columns:
            molar = float(info["molar_mass"])
            charge_abs = abs(int(info["charge"]))
            charge_df[ion] = df[ion].where(df[ion].notna(), np.nan) * charge_abs / molar

    # 阴阳离子分类
    cation_cols = [ion for ion, info in ion_info.items() if info["charge"] > 0 and ion in charge_df.columns]
    anion_cols = [ion for ion, info in ion_info.items() if info["charge"] < 0 and ion in charge_df.columns]

    cation_total = charge_df[cation_cols].sum(axis=1) if cation_cols else pd.Series(np.nan, index=df.index)
    anion_total = charge_df[anion_cols].sum(axis=1) if anion_cols else pd.Series(np.nan, index=df.index)

    # 2) SOR / NOR 计算
    nor_series = None
    sor_series = None

    if "NO3" in df.columns and "NO2" in df.columns:
        nor_values = []
        no2_values = df["NO2"].values
        for i, no3 in enumerate(df["NO3"]):
            no2 = no2_values[i]
            nor_values.append(
                calculate_nor(no3, no2) if pd.notna(no3) else None
            )
        nor_series = pd.Series(nor_values, index=df.index)

    if "SO4" in df.columns and "SO2" in df.columns:
        sor_values = []
        so2_values = df["SO2"].values
        for i, so4 in enumerate(df["SO4"]):
            so2 = so2_values[i]
            sor_values.append(
                calculate_sor(so4, so2) if pd.notna(so4) else None
            )
        sor_series = pd.Series(sor_values, index=df.index)

    # 3) 三元图（S,N,A）计算
    ternary_df = pd.DataFrame(index=df.index)
    target_ions = ["SO4", "NO3", "NH4"]
    if all(ion in df.columns for ion in target_ions):
        ion_total = df[target_ions].sum(axis=1)
        valid_mask = ion_total > 0
        ternary_df["S"] = np.where(valid_mask, df["SO4"] / ion_total, np.nan)
        ternary_df["N"] = np.where(valid_mask, df["NO3"] / ion_total, np.nan)
        ternary_df["A"] = np.where(valid_mask, df["NH4"] / ion_total, np.nan)
        coords = ternary_df.apply(
            lambda row: to_ternary_coordinates(row["S"], row["N"], row["A"])
            if pd.notna(row["S"]) else (np.nan, np.nan),
            axis=1
        )
        ternary_df["x"] = [c[0] for c in coords]
        ternary_df["y"] = [c[1] for c in coords]
    else:
        ternary_df["S"] = ternary_df["N"] = ternary_df["A"] = ternary_df["x"] = ternary_df["y"] = np.nan

    # 可用的离子列
    available_ions = [col for col in df.columns if col in ion_info]

    # 4) 构建输出数据
    series_data = [{"name": ion, "data": df[ion].fillna(np.nan).tolist()} for ion in available_ions]

    # 三元图数据
    ternary_data = []
    has_ternary = not ternary_df["x"].isna().all()
    pm25_col = "PM2.5" if "PM2.5" in df.columns else "PM2_5"
    pm25_values = df.get(pm25_col)
    for idx in ternary_df.index:
        if pd.notna(ternary_df.loc[idx, "x"]):
            ternary_data.append({
                "S": round(ternary_df.loc[idx, "S"], 4),
                "N": round(ternary_df.loc[idx, "N"], 4),
                "A": round(ternary_df.loc[idx, "A"], 4),
                "x": round(ternary_df.loc[idx, "x"], 4),
                "y": round(ternary_df.loc[idx, "y"], 4),
                "PM2.5": round(pm25_values.loc[idx], 1) if pm25_values is not None and pd.notna(pm25_values.loc[idx]) else None
            })

    # SOR/NOR 数据
    or_df = pd.DataFrame({"NOR": nor_series, "SOR": sor_series, "PM2.5": pm25_values}, index=df.index)
    sor_nor_data = []
    for idx in or_df[(or_df["SOR"].notna()) | (or_df["NOR"].notna())].index:
        sor_nor_data.append({
            "NOR": round(or_df.loc[idx, "NOR"], 4) if pd.notna(or_df.loc[idx, "NOR"]) else None,
            "SOR": round(or_df.loc[idx, "SOR"], 4) if pd.notna(or_df.loc[idx, "SOR"]) else None,
            "PM2.5": round(or_df.loc[idx, "PM2.5"], 1) if pd.notna(or_df.loc[idx, "PM2.5"]) else None
        })

    # 阴阳离子平衡 DataFrame（用于图表和balance_data）
    charge_balance_df = pd.DataFrame({"cation_total": cation_total, "anion_total": anion_total}, index=df.index)

    # 构建阴阳离子平衡数据
    balance_data = []
    for idx in charge_balance_df.index:
        if pd.notna(charge_balance_df.loc[idx, "cation_total"]) and pd.notna(charge_balance_df.loc[idx, "anion_total"]):
            balance_data.append({
                "anion_total": round(charge_balance_df.loc[idx, "anion_total"], 4),
                "cation_total": round(charge_balance_df.loc[idx, "cation_total"], 4)
            })

    # ============================================================
    # 计算统计信息（供LLM分析解读）
    # ============================================================

    # 1) 阴阳离子平衡统计
    balance_stats = {"sample_count": 0}
    if len(balance_data) > 0:
        cations = np.array([d["cation_total"] for d in balance_data])
        anions = np.array([d["anion_total"] for d in balance_data])
        valid_mask = ~np.isnan(cations) & ~np.isnan(anions)
        if valid_mask.sum() > 2:
            c_vals = cations[valid_mask]
            a_vals = anions[valid_mask]
            # 回归分析
            try:
                model = LinearRegression()
                X = a_vals.reshape(-1, 1)
                y = c_vals
                model.fit(X, y)
                r_value, p_value = stats.pearsonr(a_vals, c_vals)
                balance_stats = {
                    "sample_count": int(valid_mask.sum()),
                    "slope": round(float(model.coef_[0]), 4),
                    "intercept": round(float(model.intercept_), 4),
                    "r_squared": round(r_value ** 2, 4),
                    "correlation": round(r_value, 4),
                    "p_value": round(float(p_value), 6) if p_value > 0 else 0.0,
                    "cation_anion_ratio_mean": round(np.mean(c_vals / np.where(a_vals == 0, np.nan, a_vals)), 4) if np.any(a_vals != 0) else None,
                    "cation_mean": round(float(np.mean(c_vals)), 4),
                    "anion_mean": round(float(np.mean(a_vals)), 4),
                    "cation_std": round(float(np.std(c_vals)), 4),
                    "anion_std": round(float(np.std(a_vals)), 4),
                }
            except Exception:
                balance_stats = {"sample_count": int(valid_mask.sum()), "error": "regression_failed"}

    # 2) SOR/NOR 统计
    sor_nor_stats = {"sample_count": 0}
    if nor_series is not None or sor_series is not None:
        nor_vals = nor_series.dropna().values if nor_series is not None else np.array([])
        sor_vals = sor_series.dropna().values if sor_series is not None else np.array([])
        pm25_for_or = pm25_values.dropna().values if pm25_values is not None else np.array([])

        sor_nor_stats = {
            "sample_count": int((~nor_series.isna() | ~sor_series.isna()).sum()) if nor_series is not None or sor_series is not None else 0,
        }
        if len(nor_vals) > 0:
            sor_nor_stats["nor_mean"] = round(float(np.mean(nor_vals)), 4)
            sor_nor_stats["nor_std"] = round(float(np.std(nor_vals)), 4)
            sor_nor_stats["nor_min"] = round(float(np.min(nor_vals)), 4)
            sor_nor_stats["nor_max"] = round(float(np.max(nor_vals)), 4)
            sor_nor_stats["nor_median"] = round(float(np.median(nor_vals)), 4)
            # 判断二次转化程度
            sor_nor_stats["nor_secondary_level"] = "high" if np.mean(nor_vals) > 0.5 else ("medium" if np.mean(nor_vals) > 0.3 else "low")
        if len(sor_vals) > 0:
            sor_nor_stats["sor_mean"] = round(float(np.mean(sor_vals)), 4)
            sor_nor_stats["sor_std"] = round(float(np.std(sor_vals)), 4)
            sor_nor_stats["sor_min"] = round(float(np.min(sor_vals)), 4)
            sor_nor_stats["sor_max"] = round(float(np.max(sor_vals)), 4)
            sor_nor_stats["sor_median"] = round(float(np.median(sor_vals)), 4)
            sor_nor_stats["sor_secondary_level"] = "high" if np.mean(sor_vals) > 0.5 else ("medium" if np.mean(sor_vals) > 0.3 else "low")
        # SOR vs NOR 对比
        if len(nor_vals) > 0 and len(sor_vals) > 0:
            sor_nor_stats["sor_nor_ratio"] = round(float(np.mean(sor_vals) / np.mean(nor_vals)), 4) if np.mean(nor_vals) > 0 else None
            sor_nor_stats["secondary_transformation"] = "SO4_dominant" if np.mean(sor_vals) > np.mean(nor_vals) else ("NO3_dominant" if np.mean(nor_vals) > np.mean(sor_vals) else "balanced")

    # 3) 三元图统计（S-N-A分布）
    ternary_stats = {"sample_count": 0}
    if has_ternary and len(ternary_data) > 0:
        s_vals = np.array([d["S"] for d in ternary_data if d["S"] is not None])
        n_vals = np.array([d["N"] for d in ternary_data if d["N"] is not None])
        a_vals = np.array([d["A"] for d in ternary_data if d["A"] is not None])
        pm25_ternary = np.array([d["PM2.5"] for d in ternary_data if d["PM2.5"] is not None])

        ternary_stats = {
            "sample_count": len(ternary_data),
            "S_mean": round(float(np.mean(s_vals)), 4) if len(s_vals) > 0 else None,
            "N_mean": round(float(np.mean(n_vals)), 4) if len(n_vals) > 0 else None,
            "A_mean": round(float(np.mean(a_vals)), 4) if len(a_vals) > 0 else None,
            "S_std": round(float(np.std(s_vals)), 4) if len(s_vals) > 0 else None,
            "N_std": round(float(np.std(n_vals)), 4) if len(n_vals) > 0 else None,
            "A_std": round(float(np.std(a_vals)), 4) if len(a_vals) > 0 else None,
            "dominant_ion": "SO4" if np.mean(s_vals) > np.mean(n_vals) and np.mean(s_vals) > np.mean(a_vals) else ("NO3" if np.mean(n_vals) > np.mean(s_vals) and np.mean(n_vals) > np.mean(a_vals) else "NH4") if len(s_vals) > 0 else None,
            "secondary_inorganic_type": None,
        }
        # 判断二次无机盐类型
        if len(s_vals) > 0 and len(n_vals) > 0:
            s_ratio = np.mean(s_vals) / (np.mean(s_vals) + np.mean(n_vals)) if (np.mean(s_vals) + np.mean(n_vals)) > 0 else 0.5
            if s_ratio > 0.7:
                ternary_stats["secondary_inorganic_type"] = "SO4_dominant"  # 硫酸盐主导
            elif s_ratio < 0.3:
                ternary_stats["secondary_inorganic_type"] = "NO3_dominant"  # 硝酸盐主导
            else:
                ternary_stats["secondary_inorganic_type"] = "mixed"  # 混合型
        # PM2.5关联
        if len(pm25_ternary) > 0:
            ternary_stats["pm25_mean"] = round(float(np.mean(pm25_ternary)), 2)
            ternary_stats["pm25_max"] = round(float(np.max(pm25_ternary)), 2)
            ternary_stats["pm25_min"] = round(float(np.min(pm25_ternary)), 2)

    # 4) 离子浓度统计
    ion_stats = {}
    for ion in available_ions:
        if ion in df.columns:
            values = df[ion].dropna().values
            if len(values) > 0:
                ion_stats[ion] = {
                    "mean": round(float(np.mean(values)), 4),
                    "std": round(float(np.std(values)), 4),
                    "min": round(float(np.min(values)), 4),
                    "max": round(float(np.max(values)), 4),
                    "median": round(float(np.median(values)), 4),
                    "sum": round(float(np.sum(values)), 4),
                    "sample_count": int(len(values))
                }
            else:
                ion_stats[ion] = {"sample_count": 0}

    # 合并所有统计信息
    statistics = {
        "balance": balance_stats,
        "sor_nor": sor_nor_stats,
        "ternary": ternary_stats,
        "ions": ion_stats
    }

    # 生成专业图表
    visuals = []
    try:
        visualizer = ParticulateVisualizer()
        pm25_series = df.get("PM2.5") if "PM2.5" in df.columns else df.get("PM2_5")

        logger.info(
            "[calculate_soluble] 图表生成",
            df_columns=list(df.columns),
            pm25_series_is_none=pm25_series is None,
            pm25_notna_count=pm25_series.notna().sum() if pm25_series is not None else 0
        )

        # 【修改】不再生成"水溶性离子组分堆积时间序列与PM2.5浓度变化图"
        # 保留其他专业图表：三元图、SOR/NOR图、电荷平衡图

        if has_ternary:
            ternary_chart = visualizer.generate_ternary_chart(ternary_df, pm25_series, source_data_id=original_data_id)
            if ternary_chart:
                visuals.append(ternary_chart)

        if nor_series is not None or sor_series is not None:
            sor_nor_chart = visualizer.generate_sor_nor_chart(nor_series, sor_series, pm25_series, source_data_id=original_data_id)
            if sor_nor_chart:
                visuals.append(sor_nor_chart)

        if not cation_total.isna().all() and not anion_total.isna().all():
            balance_chart = visualizer.generate_charge_balance_chart(cation_total, anion_total, source_data_id=original_data_id)
            if balance_chart:
                visuals.append(balance_chart)
    except Exception as viz_err:
        logger.warning(f"[calculate_soluble] 图表生成失败: {viz_err}")

    metadata = {
        "generator": "calculate_soluble",
        "version": "1.0.0",
        "analysis_type": analysis_type,
        "source_data_hash": _hash_dataframe(df) if isinstance(data, pd.DataFrame) else "",
        "schema_version": "v2.0",
        "scenario": "pm_soluble_ion_analysis",
        "source_data_id": original_data_id,
    }

    logger.info(
        "[calculate_soluble] 计算完成",
        available_ions=available_ions,
        records=len(df),
        visuals_count=len(visuals)
    )

    # 生成摘要信息
    sor_mean_val = statistics.get("sor_nor", {}).get("sor_mean")
    nor_mean_val = statistics.get("sor_nor", {}).get("nor_mean")
    secondary_type = statistics.get("ternary", {}).get("secondary_inorganic_type")
    balance_r2 = statistics.get("balance", {}).get("r_squared")
    ion_count = len(available_ions)

    # 添加图片URL到summary
    summary_lines = [
        f"✅ calculate_soluble 执行完成 - 离子数量: {ion_count}, SOR均值: {sor_mean_val}, NOR均值: {nor_mean_val}, 二次无机盐类型: {secondary_type}, 阴阳离子平衡R2: {balance_r2}"
    ]

    # 如果有图表，添加图片URL
    if visuals:
        for visual in visuals:
            markdown_image = visual.get("markdown_image")
            if markdown_image:
                summary_lines.append(f"\n{markdown_image}")
                break  # 只添加第一张图

    summary = "\n".join(summary_lines)

    return {
        "status": "success",
        "success": True,
        "data": {
            "statistics": statistics,  # 统计结论
            "ternary_data": ternary_data,  # 三元图分布（核心）
            "balance_data": balance_data  # 电荷平衡数据（核心）
        },
        "metadata": metadata,
        "visuals": visuals,
        "summary": summary,
    }


# ============================================================================
# 工具包装器类（用于注册到全局工具注册表）
# ============================================================================

from app.tools.base.tool_interface import LLMTool, ToolCategory


class CalculateSolubleTool(LLMTool):
    """水溶性离子分析工具

    支持 Context-Aware V2，从 get_particulate_data 获取的标准化数据中自动提取
    components 字段进行计算。

    **重要**: 此工具需要专门的水溶性离子数据查询，必须使用正确的 question 参数。

    输入格式：UnifiedParticulateData（components 嵌套结构）
    """

    name = "calculate_soluble"
    description = "计算水溶性离子分析，自动生成三元图/SOR/NOR/电荷平衡图"
    category = ToolCategory.ANALYSIS
    version = "1.0.0"
    requires_context = True

    def __init__(self):
        function_schema = {
            "name": "calculate_soluble",
            "description": """
执行水溶性离子分析，计算阴阳离子平衡、SOR/NOR氧化速率、三元图数据。

**核心要求**:
- **必须先查询水溶性离子数据**，不能与碳组分/地壳元素混合查询
- 使用 get_particulate_data 时必须指定查询水溶性离子
- 气体数据（NO2/SO2）为必需参数，用于SOR/NOR计算

**数据获取步骤**:
1. **获取水溶性离子数据**（必须使用专门查询）：
   - 使用组件查询问题生成器: `from app.tools.query.component_query_generator import generate_component_query`
   - 生成查询问题: `question = generate_component_query("soluble", "清远市", "2025-12-24", "小时")`
   - 返回问题示例: "清远市，2025-12-24，时间粒度为小时，PM2.5组分数据，要求并发查询，要求包含 SO4（硫酸盐）、NO3（硝酸盐）、NH4（铵盐）、Cl（氯离子）、Ca（钙离子）、Mg（镁离子）、K（钾离子）、Na（钠离子）"
   - 调用: `particle_data = get_particulate_data(question=question)`

2. **获取气体数据**（必需，缺少则无法计算SOR/NOR）：
   - SOR计算需要 SO2 数据
   - NOR计算需要 NO2 数据
   - **必须调用** get_air_quality_data 获取气体数据
   - 正确示例: `gas_data = get_air_quality_data("揭阳市2025年12月24日的小时污染物数据，包含 NO2、SO2")`

3. **调用此工具**：
   - 传入 data_id（必需）和 gas_data_id（必需）

**需要的水溶性离子字段**:
- SO4（硫酸盐，SO4^2-）
- NO3（硝酸盐，NO3-）
- NH4（铵盐，NH4+）
- Cl（氯离子，Cl-）
- Ca（钙离子，Ca2+）
- Mg（镁离子，Mg2+）
- K（钾离子，K+）
- Na（钠离子，Na+）

**返回结果**:
- 阴阳离子电荷平衡数据
- 三元图（S-N-A）坐标数据
- SOR/NOR 氧化速率
- 专业图表：三元图/SOR/NOR图/电荷平衡图

**执行示例**:
```python
from app.tools.query.component_query_generator import generate_component_query

# 步骤1: 查询水溶性离子数据
question = generate_component_query("soluble", "深圳市", "2025-12-24", "小时")
ion_data = get_particulate_data(question=question)

# 步骤2: 查询气体数据
gas_data = get_air_quality_data("深圳市2025年12月24日的小时污染物数据，包含 NO2、SO2")

# 步骤3: 执行分析
result = calculate_soluble(
    data_id=ion_data["data_id"],
    gas_data_id=gas_data["data_id"]
)
```
            """.strip(),
            "parameters": {
                "type": "object",
                "properties": {
                    "data_id": {
                        "type": "string",
                        "description": "颗粒物组分数据ID（来自 get_particulate_data）"
                    },
                    "gas_data_id": {
                        "type": "string",
                        "description": "空气质量数据ID（来自 get_air_quality_data），**必需参数**，用于SOR/NOR计算，必须提供 NO2 和 SO2 数据"
                    },
                    "analysis_type": {
                        "type": "string",
                        "enum": ["full", "simple"],
                        "default": "full"
                    }
                },
                "required": ["data_id", "gas_data_id"]  # gas_data_id 改为必需
            }
        }

        super().__init__(
            name=self.name,
            description=self.description,
            category=self.category,
            version=self.version,
            requires_context=self.requires_context,
            function_schema=function_schema
        )

    async def execute(
        self,
        context: "ExecutionContext",
        data_id: str,
        gas_data_id: Optional[str] = None,
        analysis_type: str = "full",
        **kwargs
    ) -> Dict[str, Any]:
        """执行水溶性离子分析"""
        # 【关键日志】确认接收到的参数
        logger.info("[calculate_soluble] execute接收参数",
            data_id=data_id,
            gas_data_id=gas_data_id,
            data_id_length=len(data_id) if data_id else 0,
            gas_data_id_length=len(gas_data_id) if gas_data_id else 0
        )

        # Step 1: 获取标准化后的离子数据
        try:
            handle = context.get_handle(data_id)
            ion_records = context.get_data(data_id)
            if not isinstance(ion_records, list) or len(ion_records) == 0:
                return {
                    "status": "failed",
                    "success": False,
                    "data": None,
                    "metadata": {"tool_name": "calculate_soluble", "error_type": "empty_data"},
                    "summary": f"[FAIL] 数据为空或格式错误"
                }
            logger.info("[calculate_soluble] 加载离子数据", records=len(ion_records))
            if ion_records:
                first = ion_records[0]
                if hasattr(first, 'model_dump'):
                    first_dict = first.model_dump()
                else:
                    first_dict = dict(first)
                logger.info("[calculate_soluble] 离子数据首条记录",
                    keys=list(first_dict.keys())[:10],
                    has_components='components' in first_dict,
                    component_keys=list(first_dict.get('components', {}).keys()) if 'components' in first_dict else None
                )
        except KeyError:
            return {
                "status": "failed",
                "success": False,
                "data": None,
                "metadata": {"tool_name": "calculate_soluble", "error_type": "data_not_found"},
                "summary": f"[FAIL] 未找到数据 {data_id}"
            }
        except Exception as exc:
            return {
                "status": "failed",
                "success": False,
                "data": None,
                "metadata": {"tool_name": "calculate_soluble", "error": str(exc)},
                "summary": f"[FAIL] 数据加载失败: {exc}"
            }

        # Step 2: 获取气体数据（可选）
        gas_records = None
        if gas_data_id:
            try:
                gas_records = context.get_data(gas_data_id)
                if isinstance(gas_records, list) and len(gas_records) > 0:
                    logger.info("[calculate_soluble] 加载气体数据", records=len(gas_records))
            except Exception as exc:
                logger.warning(f"[calculate_soluble] 气体数据加载失败: {exc}")

        # Step 3: 合并离子和气体数据
        data_to_process = ion_records
        if gas_records:
            data_to_process = self._merge_ion_gas_records(ion_records, gas_records)

        # Step 4: 执行计算
        result = calculate_soluble(
            data=data_to_process,
            data_id=data_id,
            analysis_type=analysis_type
        )

        # Step 5: 保存分析结论（供后续Agent引用）
        if result.get("success") and context is not None:
            try:
                # 只保存可序列化的统计摘要，不保存visuals和复杂嵌套
                statistics = result.get("data", {}).get("statistics", {}) if result.get("data") else {}
                summary = {
                    "status": "success",
                    "available_ions": result.get("data", {}).get("series", []),
                    "statistics": statistics,
                    "visuals_count": len(result.get("visuals", [])),
                    "visuals": [
                        {
                            "id": v.get("id"),
                            "title": v.get("payload", {}).get("title"),
                            "type": v.get("meta", {}).get("chart_type")
                        }
                        for v in result.get("visuals", [])
                    ]
                }
                result_data_id = context.save_data(
                    data=[summary],
                    schema="particulate_analysis",
                    metadata={
                        "source_data_id": data_id,
                        "gas_data_id": gas_data_id,
                        "ion_count": len(summary.get("available_ions", [])),
                        "secondary_type": statistics.get("ternary", {}).get("secondary_inorganic_type"),
                        "balance_r2": statistics.get("balance", {}).get("r_squared"),
                        "sor_mean": statistics.get("sor_nor", {}).get("sor_mean"),
                        "nor_mean": statistics.get("sor_nor", {}).get("nor_mean")
                    }
                )
                result["data_id"] = result_data_id
            except Exception as save_err:
                logger.warning(f"[calculate_soluble] 保存失败: {save_err}")

        return result

    def _merge_ion_gas_records(
        self,
        ion_records: List[Any],
        gas_records: List[Any]
    ) -> List[Dict]:
        """合并离子和气体记录

        使用全局 DataStandardizer 进行字段映射（NO2, SO2 等字段名变体统一处理）
        """
        if not ion_records or not gas_records:
            return ion_records if ion_records else gas_records

        # 使用全局 DataStandardizer 进行字段映射
        standardizer = get_data_standardizer()

        # 转换为字典
        ion_dicts = []
        for r in ion_records:
            if hasattr(r, 'model_dump'):
                ion_dicts.append(r.model_dump())
            else:
                ion_dicts.append(dict(r))

        gas_dicts = []
        for r in gas_records:
            if hasattr(r, 'model_dump'):
                gas_dicts.append(r.model_dump())
            else:
                gas_dicts.append(dict(r))

        # 标准化所有记录（字段名变体会自动转换）
        ion_dicts = [standardizer.standardize(r) for r in ion_dicts]
        gas_dicts = [standardizer.standardize(r) for r in gas_dicts]

        # 气体数据关键字段（标准化后的字段名）
        GAS_KEY_FIELDS = ['NO2', 'SO2']

        # 按时间戳匹配
        ion_by_ts = {r.get('timestamp'): r for r in ion_dicts if r.get('timestamp')}
        gas_by_ts = {r.get('timestamp'): r for r in gas_dicts if r.get('timestamp')}

        merged = []
        for ts, ion in ion_by_ts.items():
            merged_record = ion.copy()

            # 提取 components（如果是嵌套结构）
            components = merged_record.get('components', {})
            if components:
                # 检查 components 中是否已有 NO2/SO2
                has_gas_in_components = any(f in components for f in GAS_KEY_FIELDS)
                # 检查离子记录顶层是否已有 NO2/SO2
                has_gas_in_top = any(f in merged_record for f in GAS_KEY_FIELDS)

                # 只有当离子数据中没有气体数据时，才从气体记录添加
                if not has_gas_in_components and not has_gas_in_top:
                    if ts in gas_by_ts:
                        for k, v in gas_by_ts[ts].items():
                            if k not in merged_record and k != 'timestamp':
                                merged_record[k] = v
            else:
                # 非嵌套结构，直接合并
                if ts in gas_by_ts:
                    for k, v in gas_by_ts[ts].items():
                        if k not in merged_record and k != 'timestamp':
                            merged_record[k] = v
            merged.append(merged_record)

        # 如果没有匹配，合并所有记录
        if not merged:
            merged = ion_dicts + [
                {k: v for k, v in r.items() if k != 'timestamp'}
                for r in gas_dicts if r.get('timestamp') and r.get('timestamp') not in ion_by_ts
            ]

        return merged


if __name__ == "__main__":
    # 单元测试
    test_records = [
        {
            "timestamp": "2025-12-24 01:00:00",
            "components": {
                "SO4": 8.5, "NO3": 5.2, "NH4": 13.225,
                "Ca": 0.166, "Mg": 0.024, "K": 0.535, "Na": 0.630
            },
            "PM2.5": 40.0
        },
        {
            "timestamp": "2025-12-24 02:00:00",
            "components": {
                "SO4": 9.2, "NO3": 6.1, "NH4": 14.384,
                "Ca": 0.171, "Mg": 0.024, "K": 0.664, "Na": 0.639
            },
            "PM2.5": 45.0
        },
        {
            "timestamp": "2025-12-24 03:00:00",
            "components": {
                "SO4": 7.8, "NO3": 4.5, "NH4": 11.2,
                "Ca": 0.15, "Mg": 0.02, "K": 0.5, "Na": 0.6
            },
            "PM2.5": 38.0
        }
    ]
    result = calculate_soluble(data=test_records)
    print(f"Status: {result['status']}")
    print(f"Ions: {[s['name'] for s in result['data']['series']]}")
    print(f"Visuals: {len(result.get('visuals', []))}")
    print("\n=== Statistics ===")
    print(f"Balance Stats: {result['data']['statistics']['balance']}")
    print(f"SOR/NOR Stats: {result['data']['statistics']['sor_nor']}")
    print(f"Ternary Stats: {result['data']['statistics']['ternary']}")
    print(f"Ion Stats: {result['data']['statistics']['ions']}")
