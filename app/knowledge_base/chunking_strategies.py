"""
分块策略配置

定义各种分块策略的配置和说明。
"""

from typing import Dict, Any, List

CHUNKING_STRATEGIES: Dict[str, Dict[str, Any]] = {
    "sentence": {
        "id": "sentence",
        "name": "句子分块",
        "description": "按句子边界切分，固定大小。速度快，适合大多数场景。",
        "pros": ["速度快", "简单可靠", "资源消耗低"],
        "cons": ["可能切断上下文", "语义完整性一般"],
        "recommended_for": ["通用文档", "新闻文章"],
        "default_chunk_size": 800,
        "default_overlap": 100
    },
    "semantic": {
        "id": "semantic",
        "name": "语义分块",
        "description": "基于语义相似度自动分块，保持语义完整性。使用Embedding模型判断语义边界。",
        "pros": ["语义完整", "检索精准", "上下文连贯"],
        "cons": ["速度较慢", "需要Embedding模型", "计算资源消耗大"],
        "recommended_for": ["技术文档", "研究论文", "学术报告"],
        "default_chunk_size": 800,
        "default_overlap": 100
    },
    "markdown": {
        "id": "markdown",
        "name": "Markdown分块",
        "description": "按Markdown标题层级切分，保持文档结构。",
        "pros": ["保持文档结构", "层次清晰", "适合技术文档"],
        "cons": ["仅适用于Markdown格式", "非MD格式效果差"],
        "recommended_for": ["技术文档", "API文档", "README文件"],
        "default_chunk_size": 1200,
        "default_overlap": 0
    },
    "hybrid": {
        "id": "hybrid",
        "name": "混合分块",
        "description": "先按标题层级切分，再按句子细分。支持多层次检索。",
        "pros": ["层次丰富", "检索灵活", "兼顾结构和语义"],
        "cons": ["存储量较大", "处理时间长"],
        "recommended_for": ["长篇报告", "书籍章节", "规范文档"],
        "default_chunk_size": 800,
        "default_overlap": 100,
        "hierarchy_sizes": [1200, 600, 300]
    },
    "llm": {
        "id": "llm",
        "name": "LLM智能分块",
        "description": "使用大语言模型进行智能语义分块，理解文档结构和主题边界，分块质量最高。支持本地(千问3)和线上(DeepSeek等)两种模式。",
        "pros": ["分块质量最高", "理解语义主题", "自动识别文档结构", "每段附带主题标签和上下文前缀", "支持本地/线上切换"],
        "cons": ["速度较慢", "需要LLM服务"],
        "recommended_for": ["环保政策法规", "技术规范", "重要文档", "高质量检索需求"],
        "default_chunk_size": 800,
        "default_overlap": 0,
        "llm_modes": {
            "local": {"name": "本地千问3", "max_chars": 25000, "description": "使用本地部署的千问3模型，速度快，无额外成本"},
            "online": {"name": "线上API", "max_chars": 60000, "description": "使用DeepSeek/MiniMax等线上API，上下文更长，适合超长文档"}
        }
    }
}


def get_strategy_info(strategy: str) -> Dict[str, Any]:
    """获取分块策略信息"""
    return CHUNKING_STRATEGIES.get(strategy, CHUNKING_STRATEGIES["llm"])


def get_all_strategies() -> List[Dict[str, Any]]:
    """获取所有分块策略"""
    return list(CHUNKING_STRATEGIES.values())


def get_strategy_defaults(strategy: str) -> Dict[str, int]:
    """获取分块策略的默认参数"""
    info = get_strategy_info(strategy)
    return {
        "chunk_size": info.get("default_chunk_size", 800),
        "chunk_overlap": info.get("default_overlap", 100)
    }
