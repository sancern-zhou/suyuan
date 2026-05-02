import pytest

from app.routers import expert_deliberation


@pytest.mark.asyncio
async def test_parse_default_input_files_reads_consultation_folder(tmp_path, monkeypatch):
    input_dir = tmp_path / "A会商文件"
    input_dir.mkdir()
    (input_dir / "会商数据.csv").write_text("城市,污染物,浓度\n广州,PM2.5,28\n", encoding="utf-8")
    (input_dir / "上月污染特征报告.txt").write_text("上月报告内容", encoding="utf-8")
    (input_dir / "阶段5深度分析成果.md").write_text("阶段5成果内容", encoding="utf-8")

    monkeypatch.setattr(expert_deliberation, "DEFAULT_INPUT_DIR", input_dir)

    result = await expert_deliberation.parse_default_input_files()

    assert result.consultation_tables
    assert result.consultation_tables[0].rows[0]["城市"] == "广州"
    assert "上月报告内容" in result.monthly_report_text
    assert "阶段5成果内容" in result.stage5_report_text
    assert result.warnings == []


@pytest.mark.asyncio
async def test_parse_default_input_files_warns_when_directory_missing(tmp_path, monkeypatch):
    input_dir = tmp_path / "missing"
    monkeypatch.setattr(expert_deliberation, "DEFAULT_INPUT_DIR", input_dir)

    result = await expert_deliberation.parse_default_input_files()

    assert result.consultation_tables == []
    assert result.monthly_report_text == ""
    assert result.stage5_report_text == ""
    assert "默认会商文件目录不存在" in result.warnings[0]
