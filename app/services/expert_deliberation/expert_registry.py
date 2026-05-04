"""Expert cards and deterministic matching rules."""

from .schemas import ExpertCard


def get_default_experts() -> list[ExpertCard]:
    return [
        ExpertCard(
            expert_id="monitoring_expert",
            display_name="监测数据专家",
            prompt_file="backend/config/prompts/report_expert.md",
            deliberation_mode="deliberation_reviewer",
            tags_any=["监测", "浓度", "同比", "环比", "排名", "污染过程", "AQI", "PM2.5", "O3"],
            tool_whitelist=["get_air_quality", "calculate_iaqi", "load_data_from_memory"],
        ),
        ExpertCard(
            expert_id="meteorology_expert",
            display_name="气象扩散专家",
            prompt_file="backend/config/prompts/weather_expert.md",
            deliberation_mode="deliberation_meteorology",
            tags_any=["气象", "扩散", "风速", "风向", "降水", "边界层", "静稳", "湿度", "温度"],
            tool_whitelist=["get_weather_data", "meteorological_trajectory_analysis", "load_data_from_memory"],
        ),
        ExpertCard(
            expert_id="chemistry_expert",
            display_name="组分化学专家",
            prompt_file="backend/config/prompts/chemical_expert_pm.md",
            deliberation_mode="deliberation_chemistry",
            tags_any=["组分", "VOCs", "NOx", "O3", "臭氧", "硝酸盐", "硫酸盐", "二次生成", "OC", "EC"],
            tool_whitelist=[
                "get_vocs_data",
                "get_pm25_ionic",
                "get_pm25_carbon",
                "get_pm25_crustal",
                "calculate_obm_ofp",
                "calculate_obm_full_chemistry",
                "calculate_reconstruction",
                "calculate_carbon",
                "calculate_soluble",
                "calculate_crustal",
                "load_data_from_memory",
            ],
        ),
        ExpertCard(
            expert_id="source_apportionment_expert",
            display_name="来源解析专家",
            prompt_file="backend/config/prompts/chemical_expert_pm.md",
            deliberation_mode="deliberation_chemistry",
            tags_any=["PMF", "源解析", "贡献", "工业", "交通", "扬尘", "燃烧", "源类", "排放"],
            tool_whitelist=["calculate_pm_pmf", "calculate_vocs_pmf", "calculate_pmf", "calculate_reconstruction", "load_data_from_memory"],
        ),
        ExpertCard(
            expert_id="transport_expert",
            display_name="区域传输专家",
            prompt_file="backend/config/prompts/trajectory_expert.md",
            deliberation_mode="deliberation_meteorology",
            tags_any=["轨迹", "传输", "上风向", "企业", "区域", "外来", "本地", "HYSPLIT", "风场"],
            tool_whitelist=[
                "meteorological_trajectory_analysis",
                "analyze_upwind_enterprises",
                "analyze_trajectory_sources",
                "get_weather_data",
                "load_data_from_memory",
            ],
        ),
        ExpertCard(
            expert_id="skeptic_reviewer",
            display_name="反方审查员",
            prompt_file="backend/config/prompts/report_expert.md",
            deliberation_mode="deliberation_reviewer",
            tags_any=[],
            tool_whitelist=["load_data_from_memory"],
        ),
        ExpertCard(
            expert_id="moderator_writer",
            display_name="主持统稿员",
            prompt_file="backend/config/prompts/report_expert.md",
            deliberation_mode="deliberation_reviewer",
            tags_any=[],
            tool_whitelist=["load_data_from_memory"],
        ),
    ]
