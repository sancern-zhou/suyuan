from app.tools.utility.skill_management.list_skills_tool import ListSkillsTool


def test_keyword_filter_matches_any_token_without_order_requirement():
    tool = ListSkillsTool()
    skills = [
        {
            "name": "抓取生态环境部全国环境空气质量状况页面和图片技能",
            "file": "/tmp/skill.md",
            "description": "抓取全国空气质量页面",
        },
        {
            "name": "Excel批量处理技能",
            "file": "/tmp/excel.md",
            "description": "使用 pandas 批量处理表格",
        },
    ]

    result = tool._filter_skills_by_keyword(skills, "生态环境部 抓取")

    assert [skill["name"] for skill in result] == [
        "抓取生态环境部全国环境空气质量状况页面和图片技能"
    ]


def test_keyword_filter_matches_description_token():
    tool = ListSkillsTool()
    skills = [
        {
            "name": "空气质量形势分析",
            "file": "/tmp/air.md",
            "description": "适用于会商汇报和污染过程研判",
        }
    ]

    result = tool._filter_skills_by_keyword(skills, "会商")

    assert result == skills
