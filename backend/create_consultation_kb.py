"""
预报会商知识库初始化脚本

创建会商专用知识库，支持：
1. 向量检索（语义搜索）
2. 结构化检索（元数据过滤）
3. 混合检索（向量+关键词）

使用方法：
    python create_consultation_kb.py
"""

import sys
from pathlib import Path

# 会商知识库配置


# 会商知识库配置
CONSULTATION_KB_CONFIG = {
    "name": "预报会商知识库",
    "description": """支持预报会商场景的专业知识库，包含：

1. **历史会商记录**：历次会商的纪要、决策依据、预报结论
2. **模型参数文档**：CMAQ、CAMx、WRF等模型参数说明
3. **技术规范**：HJ 633-2024等空气质量评价标准
4. **案例分析**：典型污染过程的成因分析和预报经验
5. **会商模板**：标准化的会商流程和报告模板

**元数据标签**（支持结构化检索）：
- category: 会商记录/模型参数/技术规范/案例分析/会商模板
- pollutant: PM2.5/O3/NO2/SO2/CO/PM10
- season: 春季/夏季/秋季/冬季
- year: 2023/2024/2025
- model_type: CMAQ/CAMx/WRF/NAQPMS
- region: 城市/区域名称
""",
    "kb_type": "public",  # 公共知识库，所有人可访问
    "chunking_strategy": "hybrid",  # 混合分块：先按标题，再按句子
    "chunk_size": 512,
    "chunk_overlap": 128,
    "is_default": True,  # 默认启用
    "embedding_model": "BAAI/bge-m3"  # 支持多语言和长文本
}


# 推荐的文档目录结构
RECOMMENDED_DOCS_STRUCTURE = """
backend_data_registry/consultation_kb/
├── 01_会商记录/
│   ├── 2024春季会商/
│   │   ├── 20240315_春季O3污染会商纪要.md
│   │   └── 20240420_沙尘天气会商记录.md
│   └── 2024冬季会商/
│       └── 20241201_重污染过程会商.md
├── 02_模型参数/
│   ├── CMAQ参数说明.md
│   ├── CAMx配置指南.md
│   └── WRF气象场设置.md
├── 03_技术规范/
│   ├── HJ_633-2024空气质量评价标准.md
│   └── 环境空气质量指数(AQI)技术规定.md
├── 04_案例分析/
│   ├── 2023年典型O3污染过程分析.md
│   └── 2024年春季沙尘天气案例分析.md
└── 05_会商模板/
    ├── 日会商模板.md
    ├── 周会商模板.md
    └── 月度会商模板.md
"""


async def create_consultation_kb():
    """创建会商知识库（通过API）"""
    print("\n" + "="*60)
    print("📋 预报会商知识库创建指南")
    print("="*60)

    print("\n" + "-"*60)
    print("方案1：使用API创建（推荐）")
    print("-"*60)

    kb_type = CONSULTATION_KB_CONFIG["kb_type"]
    chunking = CONSULTATION_KB_CONFIG["chunking_strategy"]
    is_default = str(CONSULTATION_KB_CONFIG["is_default"]).lower()

    # 转义description中的换行符
    description_escaped = CONSULTATION_KB_CONFIG["description"].replace("\n", "\\n").replace('"', '\\"')

    api_command = f"""curl -X POST "http://localhost:8000/knowledge-base" \\
  -H "Content-Type: application/json" \\
  -H "X-Is-Admin: true" \\
  -d '{{
    "name": "{CONSULTATION_KB_CONFIG["name"]}",
    "description": "{description_escaped}",
    "kb_type": "{kb_type}",
    "chunking_strategy": "{chunking}",
    "chunk_size": {CONSULTATION_KB_CONFIG["chunk_size"]},
    "chunk_overlap": {CONSULTATION_KB_CONFIG["chunk_overlap"]},
    "is_default": {is_default}
  }}'"""

    print(api_command)

    print("\n" + "-"*60)
    print("方案2：使用Python代码创建")
    print("-"*60)

    python_code = f"""
from app.db.database import async_session
from app.knowledge_base.service import KnowledgeBaseService

async def create_kb():
    async with async_session() as db:
        service = KnowledgeBaseService(db=db)
        kb = await service.create_knowledge_base(
            name="{CONSULTATION_KB_CONFIG["name"]}",
            description={repr(CONSULTATION_KB_CONFIG["description"])},
            kb_type="{kb_type}",
            owner_id=None,
            chunking_strategy="{chunking}",
            chunk_size={CONSULTATION_KB_CONFIG["chunk_size"]},
            chunk_overlap={CONSULTATION_KB_CONFIG["chunk_overlap"]},
            is_default={CONSULTATION_KB_CONFIG["is_default"]}
        )
        print(f"知识库ID: {{kb.id}}")
        return kb

import asyncio
asyncio.run(create_kb())
"""
    print(python_code)

    print("\n" + "-"*60)
    print("📚 推荐的文档目录结构:")
    print("-"*60)
    print(RECOMMENDED_DOCS_STRUCTURE)

    print("\n" + "-"*60)
    print("🔍 知识库使用示例（问数模式）:")
    print("-"*60)
    print("""
## 示例1：检索历史会商记录
用户问: "查找2024年春季O3污染的会商记录"
工具调用: search_knowledge_base(
    query="春季O3污染会商",
    knowledge_base_ids=["kb_id"],
    filters={"category": "会商记录", "year": "2024", "season": "春季"}
)

## 示例2：查询模型参数
用户问: "CMAQ模型的化学机制参数如何设置"
工具调用: search_knowledge_base(
    query="CMAQ化学机制参数配置",
    knowledge_base_ids=["kb_id"],
    filters={"category": "模型参数", "model_type": "CMAQ"}
)

## 示例3：检索技术规范
用户问: "HJ 633-2024标准中AQI计算方法"
工具调用: search_knowledge_base(
    query="AQI计算公式 方法",
    knowledge_base_ids=["kb_id"],
    filters={"category": "技术规范"}
)

## 示例4：查找案例分析
用户问: "有没有类似的沙尘天气案例"
工具调用: search_knowledge_base(
    query="沙尘天气 成因分析 预报",
    knowledge_base_ids=["kb_id"],
    filters={"category": "案例分析"}
)
""")

    print("\n" + "-"*60)
    print("📤 上传文档到知识库:")
    print("-"*60)
    print("""
# 使用API上传文档（替换 {kb_id} 为实际知识库ID）

curl -X POST "http://localhost:8000/knowledge-base/{kb_id}/documents" \\
  -H "Content-Type: multipart/form-data" \\
  -F "file=@会商纪要.md" \\
  -F 'metadata={"category": "会商记录", "year": "2024", "season": "春季"}'

# 或使用Python代码
from app.knowledge_base.service import KnowledgeBaseService

service = KnowledgeBaseService(db=db)
await service.upload_document(
    kb_id="{kb_id}",
    file_path="会商纪要.md",
    metadata={"category": "会商记录", "year": "2024", "season": "春季"}
)
""")


async def main():
    """主函数"""
    try:
        await create_consultation_kb()

        print("\n" + "="*60)
        print("✅ 初始化指南生成完成!")
        print("="*60)
        print(f"\n下一步操作:")
        print(f"1. 使用上述API或Python代码创建知识库")
        print(f"2. 准备会商文档，按推荐目录结构组织")
        print(f"3. 使用API上传文档到知识库")
        print(f"4. 在问数模式中使用 search_knowledge_base 工具检索")

    except Exception as e:
        print(f"\n❌ 初始化失败: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
