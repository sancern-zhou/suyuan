"""超级站组分数据语义字典（广东省超站 API 组分域的单一事实来源）。

内容来源：
- VOCs 117 物种清单：超站接口 GetSpeciesVOCAnalysis 返回字段（老项目
  D:\\vanna广东省VOCs\\广东超站接口.md 实测提取，按仪器类别归组）；
- 金属/无机元素 42 项编码：组分库 dat_station_metal DDL 字典（老项目
  D:\\Vanna3组分 data/backups ddl_export.json），超站 API GetChartAnalysis
  的 DetectionitemCodes 与该编码体系同源；
- OFP 固定参数（仪器 GUID / MIR 版本 / 因子单位 GUID）：超站接口约定值，
  必须原样传递，不允许模型改写；
- PM2.5 重构九组分与控制线：GetComponentPm25RecoveryAnalysis 返回契约。

查询工具、模式提示词、接入层测试统一从本模块取数，禁止在各处复写副本。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# VOCs 物种字典（117 项，按仪器类别归组；字段名即接口返回键名）
# ---------------------------------------------------------------------------

VOC_SPECIES_GROUPS: Dict[str, List[str]] = {
    "烷烃": [
        "乙烷", "丙烷", "异丁烷", "正丁烷", "环戊烷", "异戊烷", "正戊烷",
        "甲基环戊烷", "环己烷", "2,2-二甲基丁烷", "2,3-二甲基丁烷",
        "2,3-二甲基戊烷", "2,4-二甲基戊烷", "2-甲基戊烷", "3-甲基戊烷",
        "2-甲基己烷", "3-甲基己烷", "正己烷", "甲基环己烷", "正庚烷",
        "2,2,4-三甲基戊烷", "2,3,4-三甲基戊烷", "2-甲基庚烷", "3-甲基庚烷",
        "正辛烷", "正壬烷", "正癸烷", "十一烷", "十二烷",
    ],
    "烯烃": [
        "乙烯", "丙烯", "1-丁烯", "顺-2-丁烯", "反-2-丁烯", "异丁烯",
        "1-戊烯", "顺-2-戊烯", "反-2-戊烯", "1-己烯", "异戊二烯", "1,3-丁二烯",
    ],
    "炔烃": ["乙炔"],
    "芳香烃": [
        "苯", "甲苯", "乙苯", "间/对-二甲苯", "邻-二甲苯", "异丙苯", "正丙苯",
        "邻-乙基甲苯", "间-乙基甲苯", "对-乙基甲苯", "1,3,5-三甲基苯",
        "1,2,4-三甲苯", "1,2,3-三甲苯", "间-二乙苯", "对-二乙苯", "苯乙烯", "萘",
    ],
    "卤代烃": [
        "氯甲烷", "二氯甲烷", "三氯甲烷", "四氯化碳", "溴甲烷", "一溴二氯甲烷",
        "二溴一氯甲烷", "三溴甲烷", "氟利昂-11", "氟利昂-12", "氟利昂-113",
        "氟利昂-114", "氯乙烷", "1,1-二氯乙烷", "1,2-二氯乙烷", "1,2-二溴乙烷",
        "四氯乙烷", "1,1,1-三氯乙烷", "1,1,2-三氯乙烷", "1,2-二氯丙烷",
        "氯乙烯", "1,1-二氯乙烯", "反-1,2-二氯乙烯", "顺-1,2-二氯乙烯",
        "反-1,3-二氯丙烯", "顺-1,3-二氯丙烯", "三氯乙烯", "四氯乙烯",
        "六氯-1,3-丁二烯", "氯苯", "1,2-二氯苯", "1,3-二氯苯", "1,4-二氯苯",
        "1,2,4-三氯苯",
    ],
    "OVOCs": [
        "甲醛", "乙醛", "丙醛", "正丁醛", "戊醛", "己醛", "丙烯醛", "丁烯醛",
        "甲基丙烯醛", "苯甲醛", "间甲基苯甲醛", "丙酮", "2-丁酮",
        "4-甲基-2-戊酮", "2-己酮", "异丙醇", "乙酸乙烯酯", "乙酸乙酯",
        "甲基丙烯酸甲酯", "四氢呋喃", "1,4-二氧六环", "甲基叔丁基醚",
    ],
    "有机硫": ["二硫化碳", "氯化苄"],
}

VOC_ALL_SPECIES: List[str] = [
    species for group in VOC_SPECIES_GROUPS.values() for species in group
]

VOC_SPECIES_SET = frozenset(VOC_ALL_SPECIES)


def voc_species_group(species: str) -> Optional[str]:
    """物种所属类别；未收录物种返回 None。"""
    for group, members in VOC_SPECIES_GROUPS.items():
        if species in members:
            return group
    return None


def voc_species_catalog_text() -> str:
    """提示词/工具描述用的紧凑物种目录（按类别分组）。"""
    return "；".join(
        f"{group}（{len(members)}种）：{'、'.join(members)}"
        for group, members in VOC_SPECIES_GROUPS.items()
    )


# ---------------------------------------------------------------------------
# 金属/无机元素编码字典（GetChartAnalysis 的 DetectionitemCodes 同源体系）
# ---------------------------------------------------------------------------

# 中文名 -> (元素符号, 因子编码)；来源 dat_station_metal DDL（42 项）
METAL_ELEMENT_CODES: Dict[str, Tuple[str, str]] = {
    "铝": ("Al", "a20002"), "硅": ("Si", "a20119"), "钙": ("Ca", "a20029"),
    "铁": ("Fe", "a20111"), "钛": ("Ti", "a20095"), "钾": ("K", "a20068"),
    "锰": ("Mn", "a20055"), "锌": ("Zn", "a20104"), "铅": ("Pb", "a20044"),
    "钒": ("V", "a20101"), "砷": ("As", "a20006"), "铬": ("Cr", "a20033"),
    "铜": ("Cu", "a20041"), "硒": ("Se", "a20072"), "镍": ("Ni", "a20064"),
    "镉": ("Cd", "a20026"), "锑": ("Sb", "a20004"), "钴": ("Co", "a20038"),
    "汞": ("Hg", "a20058"), "铊": ("Tl", "a20089"), "钪": ("Sc", "a20113"),
    "磷": ("P", "a20127"), "锡": ("Sn", "a20092"), "碲": ("Te", "a20086"),
    "金": ("Au", "a20120"), "铯": ("Cs", "a20117"), "溴": ("Br", "a20115"),
    "锗": ("Ge", "a20130"), "钡": ("Ba", "a20012"), "铋": ("Bi", "a20020"),
    "铟": ("In", "a20126"), "硫": ("S", "a20128"), "铷": ("Rb", "a20131"),
    "锶": ("Sr", "a20079"), "氯": ("Cl", "a20129"), "铂": ("Pt", "a20133"),
    "铌": ("Nb", "a20125"), "银": ("Ag", "a20112"), "钼": ("Mo", "a20061"),
    "钇": ("Y", "a20132"), "钯": ("Pd", "a20114"), "镓": ("Ga", "a20116"),
}

# 微量元素/重金属默认清单（工业/交通/燃煤源指向 + calculate_trace 富集因子输入）
TRACE_ELEMENTS: List[str] = [
    "Mn", "Zn", "Pb", "V", "As", "Cr", "Cu", "Se", "Ni", "Cd", "Sb", "Co", "Hg",
]

_SYMBOL_TO_CODE: Dict[str, str] = {
    symbol: code for symbol, code in METAL_ELEMENT_CODES.values()
}


def resolve_element_codes(elements: List[str]) -> Tuple[List[str], List[str]]:
    """把元素符号或中文名解析为因子编码，返回 `(codes, unresolved)`。"""
    codes: List[str] = []
    unresolved: List[str] = []
    for element in elements:
        name = str(element).strip()
        code = _SYMBOL_TO_CODE.get(name)
        if code is None:
            entry = METAL_ELEMENT_CODES.get(name)
            code = entry[1] if entry else None
        if code:
            if code not in codes:
                codes.append(code)
        else:
            unresolved.append(name)
    return codes, unresolved


def metal_element_catalog_text() -> str:
    """提示词用的元素目录（符号=中文名）。"""
    return "、".join(f"{symbol}={name}" for name, (symbol, _) in METAL_ELEMENT_CODES.items())


# ---------------------------------------------------------------------------
# OFP 固定参数（超站接口约定值，必须原样传递）
# ---------------------------------------------------------------------------

# 类别级 OFP/类别分析接口的仪器类型（7 个固定 GUID）
OFP_DETECTION_ITEM_TYPE_GUIDS = [
    "6a62cb34-92b2-4d4b-b6f5-10445c1e31af",
    "6C168F79-8081-4689-9695-C7019DCE03F8",
    "7413B7E5-E7BC-4E25-BD0C-E46001F3E74C",
    "9efe8cff-45a7-4d4e-9057-da937b6057db",
    "bb1cd99e-0fc8-4ed0-b755-d32f355f0eae",
    "cf387372-bd39-42e1-87c6-fb34bcb78d31",
    "f7e6e6d5-08a5-4d93-9ffd-e538ed11c9b5",
]

# 物种级分析接口的仪器类型（固定单 GUID）
VOC_SPECIES_DETECTION_ITEM_TYPE_GUID = "0d93afdb-69f6-408f-b5fd-74d3925e48e5"

# OFP 计算的 MIR 系数版本（接口约定 mirVerEmun=1）
OFP_MIR_VERSION = 1

# OFP 接口的因子单位转换（固定 4 元数组，含两个空串占位）
OFP_FACTOR_UNIT_GUIDS = [
    "",
    "",
    "9b4b4b5d-c965-4300-ab13-0abb6ab1f65d",
    "40f4e59d-74f3-46dd-a5ec-dbccd93bf793",
]

OFP_CATEGORY_ORDER = ["烷烃", "烯烃", "炔烃", "芳香烃", "OVOCs", "卤代烃", "有机硫", "TVOC"]

# ---------------------------------------------------------------------------
# PM2.5 组分重构契约（GetComponentPm25RecoveryAnalysis）
# ---------------------------------------------------------------------------

RECONSTRUCTION_COMPONENTS = [
    "有机物", "硫酸盐", "硝酸盐", "铵盐", "元素碳", "氯盐", "地壳元素", "微量元素", "其他",
]

# 质量闭合控制线（重构后的质量浓度/PM2.5 比值的有效区间，接口返回值）
RECONSTRUCTION_RATIO_BAND = {"high": 1.20, "low": 0.70}

# 共享：剥离接口返回中的 *_Mark 质量标识字段（组分查询工具统一行为）
MARK_FIELD_SUFFIX = "_Mark"


def strip_mark_fields(record: Dict) -> Dict:
    """去掉单条记录里的 *_Mark 字段（质量标识不进交付数据）。"""
    if not isinstance(record, dict):
        return record
    return {k: v for k, v in record.items() if not str(k).endswith(MARK_FIELD_SUFFIX)}


def filter_mark_fields(records: List) -> List:
    """记录列表批量剥离 *_Mark 字段。"""
    return [strip_mark_fields(record) for record in records]
