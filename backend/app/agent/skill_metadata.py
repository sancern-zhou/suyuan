"""Published composer metadata for selectable skills."""

SKILL_METADATA = {
    "air_quality_data_quality_analysis": {"enabled": True, "aliases": [], "required_tools": []},
    "city_pollution_process_analysis": {"enabled": True, "aliases": [], "required_tools": []},
    "fault_work_order_analysis": {
        "enabled": True,
        "aliases": ["故障工单分析"],
        "required_tools": [
            "ops_audit_fetch_dataset", "execute_ops_sql_query", "execute_python",
            "create_report_chart", "create_report_package", "validate_report_package",
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
            "ops_audit_fetch_dataset", "ops_audit_run_rules", "ops_audit_inspect",
            "call_sub_agent", "create_report_package", "validate_report_package",
        ],
    },
    "pollution_alert_classification": {"enabled": True, "aliases": [], "required_tools": []},
    "pollution_fault_diagnosis": {"enabled": True, "aliases": [], "required_tools": []},
    "ppt_master_workflow": {
        "enabled": True,
        "aliases": [],
        "required_tools": ["read_file"],
    },
    "editable_ppt_generation": {
        "enabled": True,
        "aliases": ["高质量可编辑PPT", "源码PPT生成"],
        "name": "高质量可编辑 PPT 生成",
        "description": "从源码项目生成并多轮完善原生可编辑 PPTX",
        "entry_reference": "backend/app/tools/office/editable_ppt/references/index.md",
        "required_tools": ["manage_editable_ppt", "read_file", "edit_file", "validate_pptx"],
    },
    "routine_monitoring_analysis_expert": {"enabled": True, "aliases": [], "required_tools": []},
    "skill_template": {"enabled": False, "aliases": [], "required_tools": []},
    "top3_city_identification_rules": {"enabled": True, "aliases": [], "required_tools": []},
    "weather_analysis_expert": {"enabled": True, "aliases": [], "required_tools": []},
    "yuncheng_alert_tracing_skill": {
        "enabled": True,
        "aliases": [],
        "required_tools": ["create_report_package", "render_report_package", "validate_report_package"],
    },
    "上个月污染特征与溯源分析": {
        "enabled": True, "aliases": [], "required_tools": ["call_sub_agent"],
    },
    "广东省空气质量形势分析汇报PPT": {
        "enabled": True,
        "aliases": [],
        "required_tools": ["create_report_chart", "create_pptx_with_ppt_master"],
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
            "query_national_city_air_quality", "execute_python", "create_report_chart",
            "create_report_package", "render_report_package", "validate_report_package",
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
