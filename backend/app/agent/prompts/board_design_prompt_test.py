import json

from app.agent.prompts.board_prompt import BOARD_PROMPT_INLINE_XML_LIMIT, build_board_prompt


def test_board_prompt_includes_design_contract_theme_and_structural_digest():
    xml = """<mxfile><diagram><mxGraphModel><root>
    <mxCell id="0"/><mxCell id="1" parent="0"/>
    <mxCell id="node-a" value="入口" vertex="1" parent="1"><mxGeometry x="20" y="20" width="120" height="60" as="geometry"/></mxCell>
    </root></mxGraphModel></diagram></mxfile>"""
    prompt = build_board_prompt(
        ["create_drawio_board"],
        board_context={
            "current_xml": xml,
            "design_spec": {
                "diagram_type": "architecture",
                "story": "请求进入平台",
                "audience": "engineer",
                "detail_level": "faithful",
            },
            "theme_tokens": {"accent": "#123ABC"},
        },
    )

    assert '"diagram_type": "architecture"' in prompt
    assert '"story": "请求进入平台"' in prompt
    assert '"accent": "#123ABC"' in prompt
    assert '"node_count": 1' in prompt
    assert "优先依据 structural_digest" in prompt
    assert xml in prompt


def test_board_prompt_omits_large_xml_but_keeps_digest():
    padding = "x" * BOARD_PROMPT_INLINE_XML_LIMIT
    xml = (
        "<mxfile><diagram><mxGraphModel><root>"
        '<mxCell id="0"/><mxCell id="1" parent="0"/>'
        f'<mxCell id="large" value="{padding}" vertex="1" parent="1">'
        '<mxGeometry x="20" y="20" width="120" height="60" as="geometry"/>'
        "</mxCell></root></mxGraphModel></diagram></mxfile>"
    )
    prompt = build_board_prompt(["create_drawio_board"], board_context={"current_xml": xml})

    assert padding not in prompt
    assert "已省略原文以控制上下文" in prompt
    assert '"node_count": 1' in prompt
    assert "运行时注入权威 current_xml" in prompt


def test_board_prompt_state_is_valid_json():
    prompt = build_board_prompt(["create_drawio_board"], board_context={})
    state_text = prompt.split("## 当前运行状态\n```json\n", 1)[1].split("\n```", 1)[0]

    state = json.loads(state_text)
    assert state["design_spec"]["audience"] == "mixed"
    assert state["theme_tokens"]["accent"] == "#1677FF"
