import json

from app.tools.browser.tool import BrowserTool


def test_browser_schema_requires_guide_before_first_use_and_stays_compact():
    schema = BrowserTool().get_function_schema()
    serialized = json.dumps(schema, ensure_ascii=False, separators=(",", ":"))

    assert "首次使用 browser 前必须阅读" in schema["description"]
    assert "browser_skills_guide.md" in schema["description"]
    assert "首次使用前已读指南" in schema["parameters"]["properties"]["params"]["description"]
    assert len(serialized) <= 1300
