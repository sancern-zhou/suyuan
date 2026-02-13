"""
PyBox Integration Tool

工具接口 - 将PyBox集成模块暴露为标准工具。

功能:
- 完整RACM2化学机理OBM分析 (102物种, 504反应)
- EKMA等浓度曲线分析
- 减排情景模拟

接口兼容:
- Context-Aware V2
- UDF v2.0输出格式
"""

from __future__ import annotations
from typing import Dict, List, Any, Optional, TYPE_CHECKING
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.agent.context.execution_context import ExecutionContext

from .config import PYBOX_AVAILABLE, PyBoxConfig
from .ekma_full import FullEKMAAnalyzer
from .po3_analyzer import PO3Analyzer
from .rir_analyzer import RIRAnalyzer
from .vocs_mapper import VOCsMapper, RACM2_CLUSTER_DESCRIPTION
from .mechanism_loader import is_mechanism_available, RACM2_SPECIES

logger = structlog.get_logger()

# 检查RACM2机理可用性
RACM2_AVAILABLE = is_mechanism_available("RACM2")

# 工具元数据
TOOL_NAME = "calculate_obm_full_chemistry"
TOOL_DESCRIPTION = """
OBM/EKMA分析工具 - 使用RACM2完整化学机理

分析模式:
- ekma(标准模式): 使用预计算RBF插值(~30秒)

功能:
1. EKMA分析 - 生成VOCs-NOx-O3等浓度曲面图，确定O3敏感性类型
2. 专业图表 - 自动生成EKMA曲面图、敏感性分析图、控制建议图
3. 控制建议 - 基于敏感性分析给出量化减排建议

输入:
- vocs_data_id: VOCs小时粒度数据数据ID (必需)
- nox_data_id: NOx小时粒度数据ID (必需)
- o3_data_id: O3小时粒度数据ID (必需)
- mode: 分析模式 (ekma|po3|rir|all)

输出:
- UDF v2.0格式结果
- EKMA等浓度曲面
- 敏感性诊断和控制建议

注意:
- 使用RACM2化学机理(102物种, 504反应)
- 采用预计算加速策略(~30秒)，精度损失<5%
"""

TOOL_PARAMETERS = {
    "type": "object",
    "properties": {
        "vocs_data_id": {
            "type": "string",
            "description": "VOCs小时粒度的数据数据ID"
        },
        "nox_data_id": {
            "type": "string",
            "description": "NOx小时粒度的数据数据ID"
        },
        "o3_data_id": {
            "type": "string",
            "description": "O3小时粒度的数据数据ID"
        },
        "mode": {
            "type": "string",
            "enum": ["ekma", "po3", "rir", "all"],
            "default": "all",
            "description": "分析模式: ekma(等浓度曲线), po3(O3生成速率), rir(相对增量反应性), all(全部)，数据获取时必须强调查询小时粒度数据"
        },
        "mechanism": {
            "type": "string",
            "enum": ["RACM2", "MCM"],
            "default": "RACM2",
            "description": "化学机理 (RACM2: 102物种504反应, MCM: 简化机理)"
        },
        "grid_resolution": {
            "type": "integer",
            "enum": [11, 21, 41],
            "default": 21,
            "description": "EKMA网格分辨率: 11(超快模式), 21(快速模式，推荐), 41(标准模式)"
        },
        "o3_target": {
            "type": "number",
            "default": 75.0,
            "description": "O3控制目标值(ppb)"
        },
        "ho2_conc": {
            "type": "number",
            "description": "代表性HO2浓度 (ppt)，None表示使用估算值，建议范围10-100"
        },
        "ro2_conc": {
            "type": "number",
            "description": "代表性RO2浓度 (ppt)，None表示使用估算值，建议范围5-80"
        },
        "no_ratio": {
            "type": "number",
            "default": 0.3,
            "description": "NO/NOx比例，默认0.3，清晨可设为0.5-0.7"
        },
        "alkene_ratio": {
            "type": "number",
            "default": 0.15,
            "description": "烯烃占VOCs比例，默认0.15，城市典型范围0.05-0.25"
        }
    },
    "required": ["vocs_data_id"]
}


async def calculate_obm_full_chemistry(
    context: ExecutionContext,
    vocs_data_id: str,
    nox_data_id: Optional[str] = None,
    o3_data_id: Optional[str] = None,
    mode: str = "all",
    mechanism: str = "RACM2",
    grid_resolution: int = 21,
    o3_target: float = 75.0,
    ho2_conc: Optional[float] = None,
    ro2_conc: Optional[float] = None,
    no_ratio: float = 0.3,
    alkene_ratio: float = 0.15
) -> Dict[str, Any]:
    """
    执行OBM分析（预计算加速模式）

    Args:
        context: 执行上下文
        vocs_data_id: VOCs数据ID
        nox_data_id: NOx数据ID
        o3_data_id: O3数据ID
        mode: 分析模式 (ekma|po3|rir|all)
        mechanism: 化学机理 (RACM2|MCM)
        grid_resolution: EKMA网格分辨率 (11|21|41)
            - 11: 超快模式，121点
            - 21: 快速模式，441点 (推荐)
            - 41: 标准模式，1681点
        o3_target: O3控制目标值
        ho2_conc: 代表性HO2浓度 (ppt)，None表示使用估算值
        ro2_conc: 代表性RO2浓度 (ppt)，None表示使用估算值
        no_ratio: NO/NOx比例，默认0.3
        alkene_ratio: 烯烃占VOCs比例，默认0.15

    Returns:
        UDF v2.0格式结果
    """
    # 验证grid_resolution有效性
    if grid_resolution not in [11, 21, 41]:
        grid_resolution = 21  # 默认使用21

    # 只在debug级别记录开始信息
    logger.debug(
        "obm_full_chemistry_started",
        grid_resolution=grid_resolution
    )
    
    try:
        # 1. 加载数据
        vocs_data = await _load_data(context, vocs_data_id, "vocs")
        nox_data = await _load_data(context, nox_data_id, "nox") if nox_data_id else []
        o3_data = await _load_data(context, o3_data_id, "o3") if o3_data_id else []
        
        if not vocs_data:
            return {
                "status": "failed",
                "success": False,
                "data": None,
                "metadata": {
                    "schema_version": "v2.0",
                    "generator": "calculate_obm_full_chemistry",
                    "error_type": "data_not_found"
                },
                "summary": f"无法加载VOCs数据: {vocs_data_id}"
            }
        
        results = {}
        visuals = []

        # 2. EKMA分析
        if mode in ["ekma", "all"]:
            # 标准模式：使用RACM2化学机理
            ekma_analyzer = FullEKMAAnalyzer(mechanism=mechanism)
            ekma_result = ekma_analyzer.analyze(
                vocs_data=vocs_data,
                nox_data=nox_data,
                o3_data=o3_data,
                grid_resolution=grid_resolution
            )
            results["ekma"] = ekma_result.get("data")
            visuals.extend(ekma_result.get("visuals", []))

        # 3. PO3分析 (O3生成速率)
        if mode in ["po3", "all"]:
            try:
                po3_analyzer = PO3Analyzer(
                    ho2_conc=ho2_conc,
                    ro2_conc=ro2_conc,
                    no_ratio=no_ratio,
                    alkene_ratio=alkene_ratio
                )
                po3_result = po3_analyzer.analyze(
                    vocs_data=vocs_data,
                    nox_data=nox_data,
                    o3_data=o3_data
                )
                if po3_result.get("success"):
                    results["po3"] = po3_result.get("data")
                    visuals.extend(po3_result.get("visuals", []))
            except Exception as e:
                logger.debug(f"po3_analysis_failed: {e}")

        # 5. RIR分析 (相对增量反应性)
        if mode in ["rir", "all"]:
            try:
                rir_analyzer = RIRAnalyzer()
                rir_result = rir_analyzer.analyze(
                    vocs_data=vocs_data,
                    nox_data=nox_data,
                    o3_data=o3_data
                )
                if rir_result.get("success"):
                    results["rir"] = rir_result.get("data")
                    visuals.extend(rir_result.get("visuals", []))
            except Exception as e:
                logger.debug(f"rir_analysis_failed: {e}")

        # 6. 构建输出
        # 获取敏感性信息
        sensitivity = results.get("ekma", {}).get("sensitivity", {})
        po3_data = results.get("po3", {})
        rir_data = results.get("rir", {})

        summary_parts = []
        if sensitivity:
            sens_type_cn = {
                "VOCs-limited": "VOCs控制型",
                "NOx-limited": "NOx控制型",
                "transitional": "过渡区"
            }.get(sensitivity.get("type"), "未知")
            summary_parts.append(f"敏感性: {sens_type_cn}")

        if po3_data:
            stats = po3_data.get("statistics", {})
            max_po3 = stats.get("max_po3", 0)
            summary_parts.append(f"最大P(O3): {max_po3:.1f}ppb/h")

        if rir_data:
            regime = rir_data.get("regime", "")
            if regime:
                summary_parts.append(f"RIR诊断: {regime}")

        summary = "OBM分析完成(预计算加速模式)。" + "，".join(summary_parts)

        # 5. 保存分析结果数据记录（符合UDF规范）
        from datetime import datetime
        result_record = {
            "mode": mode,
            "mechanism": mechanism,
            "results": results,
            "timestamp": datetime.now().isoformat()
        }

        data_id = context.save_data(
            data=[result_record],  # 保存数据记录列表
            schema="obm_full_chemistry_result",
            metadata={
                "mode": mode,
                "mechanism": mechanism,
                "mechanism_info": {
                    "name": mechanism,
                    "num_species": 102 if mechanism == "RACM2" else 43,
                    "num_reactions": 504 if mechanism == "RACM2" else 0,
                    "grid_resolution": grid_resolution
                },
                "pybox_available": PYBOX_AVAILABLE,
                "source_data_ids": [vocs_data_id, nox_data_id, o3_data_id]
            }
        )

        # 6. 构建UDF v2.0输出格式
        output = {
            "status": "success",
            "success": True,
            "data": results,
            "data_id": data_id,
            "visuals": visuals,
            "metadata": {
                "schema_version": "v2.0",
                "generator": "calculate_obm_full_chemistry",
                "generator_version": "2.0.0",
                "mode": mode,
                "mechanism": mechanism,
                "mechanism_info": {
                    "name": mechanism,
                    "num_species": 102 if mechanism == "RACM2" else 43,
                    "num_reactions": 504 if mechanism == "RACM2" else 0,
                    "grid_resolution": grid_resolution,
                    "precision_desc": "预计算RBF插值，~30秒"
                },
                "source_data_ids": [vocs_data_id, nox_data_id, o3_data_id]
            },
            "summary": summary
        }
        
        logger.debug("obm_full_chemistry_completed", data_id=data_id)

        return output
        
    except Exception as e:
        logger.error("obm_full_chemistry_failed", error=str(e), exc_info=True)
        return {
            "status": "failed",
            "success": False,
            "data": None,
            "metadata": {
                "schema_version": "v2.0",
                "generator": "calculate_obm_full_chemistry",
                "error_type": "execution_failed",
                "error_message": str(e)
            },
            "summary": f"OBM分析失败: {str(e)}"
        }


async def _load_data(
    context: ExecutionContext,
    data_id: Optional[str],
    data_type: str
) -> List[Dict]:
    """加载数据"""
    if not data_id:
        return []
    
    try:
        data = context.get_raw_data(data_id)

        # 处理不同的数据格式
        if isinstance(data, list):
            result = data
        elif isinstance(data, dict):
            # UDF v2.0格式: {"data": [...], "metadata": {...}}
            if "data" in data and isinstance(data["data"], list):
                result = data["data"]
            # 另一种格式: {"records": [...]}
            elif "records" in data and isinstance(data["records"], list):
                result = data["records"]
            # VOCs特殊格式：可能是 {species1: [values], species2: [values]}
            # 检查第一个值是否是列表，如果是则转换为记录列表
            elif data and all(isinstance(v, list) for v in list(data.values())[:3] if not isinstance(v, (dict, str))):
                # 转换为记录列表格式
                num_records = max(len(v) for v in data.values() if isinstance(v, list))
                result = []
                for i in range(num_records):
                    record = {}
                    for key, values in data.items():
                        if isinstance(values, list) and i < len(values):
                            record[key] = values[i]
                    if record:
                        result.append(record)
            else:
                # 整个字典可能就是单条记录
                result = [data]
        else:
            result = []

        return result
    except Exception as e:
        logger.debug(f"load_{data_type}_data_failed: {e}")
        return []


class CalculateOBMFullChemistryTool(LLMTool):
    """
    完整化学机理OBM分析工具

    使用RACM2机理(102物种, 504反应)进行OBM分析，
    包括EKMA等浓度曲线分析和减排情景模拟。
    """

    def __init__(self):
        super().__init__(
            name=TOOL_NAME,
            description=TOOL_DESCRIPTION,
            category=ToolCategory.ANALYSIS,
            function_schema={
                "name": TOOL_NAME,
                "description": TOOL_DESCRIPTION,
                "parameters": TOOL_PARAMETERS
            },
            version="1.0.0",
            requires_context=True
        )

    async def execute(
        self,
        context: "ExecutionContext",
        vocs_data_id: str,
        nox_data_id: Optional[str] = None,
        o3_data_id: Optional[str] = None,
        mode: str = "all",
        mechanism: str = "RACM2",
        grid_resolution: int = 21,
        o3_target: float = 75.0,
        ho2_conc: Optional[float] = None,
        ro2_conc: Optional[float] = None,
        no_ratio: float = 0.3,
        alkene_ratio: float = 0.15,
        **kwargs
    ) -> Dict[str, Any]:
        """执行OBM分析（预计算加速模式）"""
        return await calculate_obm_full_chemistry(
            context=context,
            vocs_data_id=vocs_data_id,
            nox_data_id=nox_data_id,
            o3_data_id=o3_data_id,
            mode=mode,
            mechanism=mechanism,
            grid_resolution=grid_resolution,
            o3_target=o3_target,
            ho2_conc=ho2_conc,
            ro2_conc=ro2_conc,
            no_ratio=no_ratio,
            alkene_ratio=alkene_ratio
        )


# 工具注册信息（兼容旧版注册方式）
TOOL_REGISTRATION = {
    "name": TOOL_NAME,
    "description": TOOL_DESCRIPTION,
    "parameters": TOOL_PARAMETERS,
    "function": calculate_obm_full_chemistry,
    "requires_context": True,
    "category": "analysis",
    "tags": ["obm", "ekma", "ozone", "chemistry", "pybox", "racm2"]
}
