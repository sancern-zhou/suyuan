# AGENTS

本项目现在只保留“千里马招投标固定工作流”相关代码、脚本、测试和数据。

## 项目目标

围绕千里马网站完成指定日期、指定关键词的招投标信息闭环：

1. 抓取列表候选并落库。
2. 使用 LLM 对候选进行语义初筛。
3. 对命中候选抓取详情页。
4. 使用 LLM 完成结构化字段抽取。
5. 使用详情正文进行 LLM 二次复核。
6. 将最终有效公告保存在 SQLite。

## 当前结构

```text
context-engineering-intro/
├── src/tenders/                         # 核心模块
├── scripts/
│   ├── run_qianlima_tender_workflow.py  # 一键分阶段工作流入口
│   ├── resume_pending_tenders.py        # pending/accepted-missing 续跑
│   └── revalidate_tender_notices.py     # 已入库详情正文复核
├── tests/                               # 招投标工作流相关测试
├── data/
│   ├── qianlima_storage_state.json
│   ├── tenders_20260630_llm_full.db
│   └── tenders_20260630_llm_full.before_revalidate.db
├── .env
├── requirements.txt
├── pytest.ini
└── TASK.md
```

## 开发规则

- 所有用户沟通使用中文。
- 代码注释使用中文。
- 运行 Python 命令时使用 `venv_windows`。
- 生成的测试脚本禁止包含 emoji 表情图片。
- 未经用户要求，不主动生成报告文档。
- 修改逻辑后运行相关 pytest。
- 不要把密钥、账号、密码打印到回复里。

## 常用命令

```powershell
.\venv_windows\Scripts\python.exe .\scripts\run_qianlima_tender_workflow.py --sqlite-db data\tenders_20260630_llm_full.db --stats-only
.\venv_windows\Scripts\python.exe -m pytest .\tests\
```
