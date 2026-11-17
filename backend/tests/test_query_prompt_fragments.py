"""报告 DAG 监测问数子模式的项目片段注入契约。

共享 query_data_prompt builder 不写死任何项目内容；项目专属路由口径（中台视图、
地名规则）经 backend.prompt_fragment_files 声明的片段文件在"项目补充口径"锚点
追加，memory_context 注入行为不受影响。
"""

from app.agent.prompts import query_data_prompt as qdp


def _with_fragment(monkeypatch, segment_id, text):
    monkeypatch.setattr(qdp, "_project_fragment", lambda sid: text if sid == segment_id else None)


def test_station_prompt_appends_project_fragment_and_keeps_memory_context(monkeypatch):
    _with_fragment(monkeypatch, "query_monitoring_station", "国控站日值统一走中台 v_s_d_app_145。")

    prompt = qdp.build_query_monitoring_station_prompt([], memory_context="MEMORY_CTX_MARKER")

    assert "## 项目补充口径" in prompt
    assert "国控站日值统一走中台 v_s_d_app_145。" in prompt
    # memory_context 注入行为不受片段注入影响（DAG 节点记忆上下文契约）
    assert "MEMORY_CTX_MARKER" in prompt
    # 共享默认能力边界保持中性（不含项目地名口径）
    assert "项目口径" not in prompt.split("## 项目补充口径")[0]


def test_city_prompt_appends_project_fragment(monkeypatch):
    _with_fragment(monkeypatch, "query_monitoring_city", "许昌本市数据不走城市发布历史。")

    prompt = qdp.build_query_monitoring_city_prompt([])

    assert "许昌本市数据不走城市发布历史。" in prompt
    assert "## 项目补充口径" in prompt


def test_prompts_stay_neutral_without_fragment(monkeypatch):
    monkeypatch.setattr(qdp, "_project_fragment", lambda sid: None)

    station = qdp.build_query_monitoring_station_prompt([])
    city = qdp.build_query_monitoring_city_prompt([])

    assert "## 项目补充口径" not in station
    assert "## 项目补充口径" not in city
    assert "v_s_d_app_145" not in station
    assert "v_c_d_sb_145" not in city


def test_fragment_loader_reads_declared_project_file(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from app.agent.prompts.project_prompt import load_project_prompt_fragment

    fragment_file = tmp_path / "fragment.md"
    fragment_file.write_text("项目口径片段内容", encoding="utf-8")
    context = SimpleNamespace(
        manifest=SimpleNamespace(
            project="demo-project",
            backend=SimpleNamespace(
                prompt_fragment_files={"query_monitoring_city": str(fragment_file)}
            ),
        )
    )
    # 片段文件必须位于项目目录内——tmp_path 不在 projects/ 下，应拒绝
    import pytest
    from app.project_config import ProjectConfigError

    with pytest.raises(ProjectConfigError):
        load_project_prompt_fragment("query_monitoring_city", context)
