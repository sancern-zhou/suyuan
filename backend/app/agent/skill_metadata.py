"""Published composer metadata for selectable skills."""

SKILL_METADATA = {
    "air_quality_data_quality_analysis": {"enabled": True, "aliases": [], "required_tools": []},
    "analysis_report_workflow": {
        "enabled": True,
        "aliases": ["分析报告工作流", "报告生成工作流", "通用报告技能"],
        "required_tools": ["read_file", "execute_python", "create_business_chart"],
    },
    "archify": {
        "enabled": True,
        "aliases": [
            "架构图",
            "流程图",
            "时序图",
            "序列图",
            "数据流图",
            "生命周期图",
            "Mermaid美化",
            "Mermaid转换",
        ],
        "required_tools": [
            "read_file",
            "write_file",
            "edit_file",
            "list_directory",
            "search_files",
            "grep",
        ],
    },
    "city_pollution_process_analysis": {"enabled": True, "aliases": [], "required_tools": []},
    "fault_work_order_analysis": {
        "enabled": True,
        "aliases": ["故障工单分析"],
        "required_tools": [
            "ops_audit_fetch_dataset", "execute_ops_sql_query", "execute_python",
            "create_business_chart", "create_report_package",
        ],
    },
    "operation_availability_root_cause_analysis": {
        "enabled": True,
        "aliases": ["运维有效率归因", "断数故障归因"],
        "required_tools": [
            "call_sub_agent", "ops_audit_fetch_dataset", "ops_audit_run_rules",
            "execute_ops_sql_query",
        ],
    },
    "ops_work_order_audit": {
        "enabled": True,
        "aliases": ["运维工单审核"],
        "required_tools": [
            "read_file", "ops_audit_fetch_dataset", "ops_audit_run_rules", "ops_audit_inspect",
            "create_report_package",
        ],
    },
    "ops_audit_retrospective": {
        "enabled": True,
        "aliases": ["审核复盘", "清单对账", "自我迭代复盘"],
        "required_tools": [
            "ops_audit_reconcile_checklist", "ops_audit_retrospective_stats",
            "read_file", "write_file",
        ],
    },
    "pollution_alert_classification": {"enabled": True, "aliases": [], "required_tools": []},
    "pollution_fault_diagnosis": {"enabled": True, "aliases": [], "required_tools": []},
    "ppt_master_workflow": {
        "enabled": True,
        "aliases": [],
        "required_tools": ["read_file"],
    },
    "pptx_authoring": {
        "enabled": True,
        "aliases": ["PPT设计", "PPT制作", "幻灯片生成", "python-pptx", "自由PPT"],
        "name": "PPT 设计与生成技能",
        "description": "用 execute_python 编写 python-pptx 代码自由创作高质量 PPTX，配合 validate_pptx 渲染验收闭环",
        "required_tools": ["read_file", "execute_python", "validate_pptx"],
    },
    "docx_authoring": {
        "enabled": True,
        "aliases": ["Word设计", "Word制作", "文档生成", "python-docx", "自由Word"],
        "name": "Word 文档创作技能",
        "description": "用 execute_python 编写 python-docx 代码自由创作非公文 Word 交付文档，配合 validate_office 渲染验收闭环",
        "required_tools": ["read_file", "execute_python", "validate_office"],
    },
    "xlsx_authoring": {
        "enabled": True,
        "aliases": ["Excel设计", "Excel制作", "表格生成", "openpyxl", "台账"],
        "name": "Excel 表格设计技能",
        "description": "用 execute_python + openpyxl 设计高质量交付 Excel，继承 data_manual 规则并配合 validate_office 读回校验闭环",
        "required_tools": ["read_file", "execute_python", "validate_office"],
    },
    "routine_monitoring_analysis_expert": {"enabled": True, "aliases": [], "required_tools": []},
    "skill_template": {"enabled": False, "aliases": [], "required_tools": []},
    "top3_city_identification_rules": {"enabled": True, "aliases": [], "required_tools": []},
    "上个月污染特征与溯源分析": {
        "enabled": True, "aliases": [], "required_tools": ["call_sub_agent"],
    },
    "广东省空气质量形势分析汇报PPT": {
        "enabled": True,
        "aliases": [],
        # 2026-11 起 PPT 管线退役，改走 pptx_authoring 技能路线（技能正文需在 project/guangdong 分支同步更新）
        "required_tools": ["create_business_chart", "read_file", "execute_python", "validate_pptx"],
    },
    "抓取生态环境部全国环境空气质量状况页面和图片技能": {
        "enabled": True,
        "aliases": [],
        "required_tools": ["browser", "write_file", "create_report_package"],
    },
    "生态环境招投标市场分析": {
        "enabled": True,
        "aliases": ["招投标市场分析", "招投标半月报", "招投标月报", "招投标市场日报生成", "招投标日报"],
        "required_tools": [
            "call_sub_agent", "search_files", "read_file", "read_docx",
            "list_session_resources", "web_search", "web_fetch", "write_file",
            "execute_tender_sql_query", "query_national_province_air_quality",
            "execute_python", "create_business_chart",
            "create_report_package",
        ],
    },
    "昨日污染特征与溯源分析": {
        "enabled": True, "aliases": [], "required_tools": ["call_sub_agent"],
    },
    "污染推理分析": {
        "enabled": True,
        "aliases": ["污染深度推理"],
        "required_tools": ["read_file", "call_sub_agent", "write_file"],
    },
}
