"""Business types and content tags curated from the user's 283-row workbook.

Keep the existing project_category API stable; these are independent business
dimensions persisted in extraction_meta_json, not replacements for SQL enums.
"""
from __future__ import annotations

BUSINESS_TYPES = {
    "运维服务": "以已有站点、仪器、平台或软件持续运行维护为主要交付。",
    "防控服务项目": "以污染防控、精细化管控、驻点专家或改善方案等技术服务为主。",
    "大气业务综合项目": "包含多项大气业务且无明确单一主交付；不能仅因多标签就归综合。",
    "走航项目": "以车载、移动走航监测或走航分析为主要交付。",
    "园区污染源": "以园区污染源监测、溯源或监管能力建设为主；采购人位于园区不足以判定。",
    "预报": "以预测预报、预警模型或预测系统建设为主；已有预报系统纯运维优先运维服务。",
    "执法监管": "以执法、非现场监管或执法支撑系统为主要交付。",
    "颗粒物与臭氧协同控制项目": "明确涉及颗粒物与臭氧协同防控；仅出现一种污染物不足以判定。",
    "设备采购": "以仪器、设备购置为主要交付，包含安装不自动等于治理工程。",
    "组分网": "以颗粒物或大气组分监测网络建设为主；现有组分网纯运维优先运维服务。",
    "双碳/温室": "以温室气体、碳监测或碳排放清单为主要业务。",
    "调度": "以污染巡查指挥调度体系或服务为主。",
    "站房": "以监测站房建设、改造为主，与污染治理施工区分。",
    "其他环保业务": "属于水、土、固废、生态、治理工程等环保业务但不适用上述类型；是否排除另按exclusion规则判断。",
    "非环保配套": "明确为办公、后勤等通用采购；是否排除另按exclusion规则判断。",
    "待确认": "证据不足以确定类型，保留待补充，不强行分类。",
}

CONTENT_TAGS = {
    "平台": "平台或信息系统建设、升级、使用服务",
    "站点运维": "监测站点或网络运行维护",
    "报告服务": "明确交付分析报告、专题报告等，不从技术服务泛推",
    "走航服务": "移动走航监测或分析",
    "驻点/技术": "驻点专家或专业技术支撑",
    "软件运维": "已有软件、信息系统维护",
    "设备采购运维": "设备采购、维修、校验或运行维护，原表合并标签不拆分",
    "咨询服务": "咨询、评估或方案建议",
    "溯源": "污染来源追踪、来源解析",
    "预报/预警": "预测预报或预警",
    "卫星/遥感监测": "卫星、雷达或其他遥感监测",
    "污染巡查调度": "污染巡查、指挥调度",
    "执法": "执法监管、检查或执法辅助",
    "数据质控分析服务": "数据审核、质量控制或分析服务",
    "AI": "明确涉及人工智能、智能体、大模型或机器学习，智慧平台不自动等于AI",
    "清单编制": "排放清单、污染源清单编制",
    "站房建设": "监测站房建设或改造",
    "验收": "验收服务；公告标题是验收公告不代表采购了验收服务",
    "安全测评": "等保、密评、安全测评",
    "采样服务": "明确的采样服务",
}


def classification_prompt() -> dict:
    return {
        "task": "对已获取公告分类、打标签并抽取字段，面向整个环保领域，同时识别明确的工程治理、办公采购和实验室仪器采购。水、土、固废、工程治理等领域名称本身不构成排除依据；按实际采购交付判断。",
        "business_type_options": BUSINESS_TYPES,
        "content_tag_options": CONTENT_TAGS,
        "rules": [
            "exclusion_category仅允许engineering_remediation、office_procurement、laboratory_instruments或null；分类与排除在同一次响应中完成。",
            "laboratory_instruments：主要交付为实验室内使用的分析、检测仪器采购，如实验室色谱、质谱、光谱、总有机碳分析仪等。采购人是实验室不充分；现场空气站、超级站、走航、在线监测设备，以及检测服务、仪器维修运维不按实验室仪器采购排除。用途不明确时保留待确认。",
            "engineering_remediation：主要交付明确为污染治理设施施工、治理工艺改造、脱硫脱硝除尘或废水处理设施建设、土壤修复施工等，含明确用于治理工艺的设备及其运营维护；不是环境监测仪器。",
            "office_procurement：主要交付明确为普通办公家具、文印耗材、通用办公终端、办公装修或后勤保障；不能因采购人是办公室而排除。",
            "保护监测站建设和运维、现场监测设备采购维修、软件平台、预报预警、走航溯源、防治技术支撑、咨询、评估、检测服务；实验室仪器购置按laboratory_instruments单独判断。仅背景提到工程、治理、办公室，或代理机构名称含工程，不得排除。",
            "工程治理与监测技术服务混合且主交付不明、标题笼统或信息不足时保留待确认。不得以非大气、缺金额、无标签或environment_relevance=false作为排除依据。",
            "建议排除必须给出exclusion_reason、exclusion_evidence（标题或标的物的连续原文引用）、exclusion_confidence（0到1）；只有证据明确且置信度至少0.9才建议排除，其他情况exclusion_category=null。",
            "business_type对应Excel类型，选择一个主类型；content_tags对应Excel内容，可多选，只用上述标签。",
            "以采购主要交付确定类型；维护预报平台归运维服务，标签可含平台、软件运维、预报/预警。",
            "综合项目需正文支持多业务组合；不能因标题写大气就默认综合。",
            "逐标签提供原文证据tag_evidence；不从相似项目、表格样例或行业惯例推断未出现的服务。",
            "表格标签是词表而非事实金标准；原表缺失值不代表排除，原标签有歧义时按当前公告证据判断。",
            "信息不足用待确认或空标签；classification_status为needs_review，保留已确定字段。",
            "environment_relevance只描述是否环保：true/false/null，不能作为删除或不入库的依据。",
            "候选公示、预成交、评审不能记为最终中标；更正、合同分别标记notice_stage，避免重复金额统计。",
            "只使用输入中的事实，未知金额留空，预算不等于中标金额，零值不代表免费中标。",
        ],
        "output_fields": {
            "exclusion_category": "engineering_remediation|office_procurement|laboratory_instruments|null",
            "exclusion_reason": "排除原因；不排除时为空",
            "exclusion_evidence": "标题或标的物中的连续原文证据；不排除时为空",
            "exclusion_confidence": "number，0到1",
            "business_type": "上述类型之一",
            "content_tags": ["上述内容标签，可为空"],
            "tag_evidence": {"标签": "输入原文中的依据"},
            "classification_status": "classified|needs_review",
            "environment_relevance": "boolean|null",
            "notice_stage": "final_result|candidate|correction|contract|tender|other|unknown",
        },
    }


def normalize_classification(data: dict) -> dict:
    business_type = data.get("business_type")
    if not isinstance(business_type, str) or business_type not in BUSINESS_TYPES:
        business_type = "待确认"
    supplied = data.get("content_tags")
    supplied = supplied if isinstance(supplied, list) else []
    evidence = data.get("tag_evidence")
    evidence = evidence if isinstance(evidence, dict) else {}
    tags = list(dict.fromkeys(t for t in supplied if isinstance(t, str) and t in CONTENT_TAGS))
    valid_evidence = {t: evidence[t].strip() for t in tags if isinstance(evidence.get(t), str) and evidence[t].strip()}
    status = data.get("classification_status")
    if status != "classified" or business_type == "待确认" or len(valid_evidence) != len(tags):
        status = "needs_review"
    stage = data.get("notice_stage")
    if not isinstance(stage, str) or stage not in {"final_result", "candidate", "correction", "contract", "tender", "other", "unknown"}:
        stage = "unknown"
    exclusion = data.get("exclusion_category")
    confidence = data.get("exclusion_confidence")
    confidence = float(confidence) if type(confidence) in (int, float) and 0 <= confidence <= 1 else 0.0
    return dict(business_type=business_type, content_tags=tags,
                exclusion_category=exclusion if isinstance(exclusion, str) and exclusion in {"engineering_remediation", "office_procurement", "laboratory_instruments"} else None,
                exclusion_reason=data.get("exclusion_reason") if isinstance(data.get("exclusion_reason"), str) else "",
                exclusion_evidence=data.get("exclusion_evidence") if isinstance(data.get("exclusion_evidence"), str) else "",
                exclusion_confidence=confidence,
                tag_evidence=valid_evidence, classification_status=status,
                notice_stage=stage, taxonomy_version="xlsx-2026-09-21-v2")


def legacy_category_from_classification(classification: dict, title: str) -> str:
    """Conservative compatibility mapping when the old category is missing."""
    business_type = classification.get("business_type")
    mapping = {
        "运维服务": "operation_maintenance", "防控服务项目": "environment_consulting",
        "走航项目": "environment_monitoring", "执法监管": "law_enforcement_support",
        "设备采购": "equipment_supplies", "预报": "environment_consulting",
        "组分网": "environment_monitoring", "调度": "digital_platform",
        "颗粒物与臭氧协同控制项目": "environment_consulting",
    }
    if business_type in mapping:
        return mapping[business_type]
    if business_type == "双碳/温室":
        return "environment_monitoring" if any(t in title for t in ("监测", "检测")) else "environment_consulting"
    if business_type == "其他环保业务":
        if any(t in title for t in ("监测", "检测", "溯源")):
            return "environment_monitoring"
        if "平台" in classification.get("content_tags", []):
            return "digital_platform"
    return "other_environment_procurement"
