from pathlib import Path


ROOT = Path(__file__).resolve().parents[2] / "app" / "agent"


def test_active_graph_prompts_do_not_reference_legacy_cognitive_map_runtime():
    sources = "\n".join(
        (ROOT / relative).read_text(encoding="utf-8")
        for relative in (
            "context/context_builder.py",
            "prompts/graph_prompt.py",
            "prompts/tool_registry.py",
        )
    )
    assert "cognitive_maps" not in sources
    assert "认知地图面板" not in sources
    assert "认知地图 REST API" not in sources
    assert "认知地图图谱编辑" not in sources
