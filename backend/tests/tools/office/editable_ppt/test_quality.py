from app.tools.office.editable_ppt.quality import build_editable_ppt_gate


def test_gate_blocks_forbidden_raster_even_when_visual_qa_passes():
    result = build_editable_ppt_gate(
        compile_report={"forbiddenRasterFallbacks": 1, "issues": []},
        validation={"gate": {"status": "passed", "passed": True}, "issues": []},
    )
    assert result.status == "needs_revision"
    assert result.blocking is True
    assert result.issues[0]["code"] == "FORBIDDEN_RASTER_FALLBACK"


def test_gate_passes_only_clean_compile_and_validation():
    result = build_editable_ppt_gate(
        compile_report={"forbiddenRasterFallbacks": 0, "issues": []},
        validation={"success": True, "issues": []},
    )
    assert result.status == "passed"
    assert result.blocking is False
