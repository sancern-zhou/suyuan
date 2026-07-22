from app.tools.office.editable_ppt.quality import build_editable_ppt_gate


def test_gate_blocks_forbidden_raster_even_when_visual_qa_passes():
    result = build_editable_ppt_gate(
        compile_report={"editable": "strict", "forbiddenRasterFallbacks": 1, "issues": []},
        validation={"gate": {"status": "passed", "passed": True}, "issues": []},
    )
    assert result.status == "needs_revision"
    assert result.blocking is True
    assert result.issues[0]["code"] == "FORBIDDEN_RASTER_FALLBACK"


def test_gate_passes_only_clean_compile_and_validation():
    result = build_editable_ppt_gate(
        compile_report={"editable": "strict", "forbiddenRasterFallbacks": 0, "issues": []},
        validation={"success": True, "issues": []},
    )
    assert result.status == "passed"
    assert result.blocking is False


def test_gate_rejects_missing_or_non_strict_compile_evidence():
    validation = {"success": True, "issues": []}
    assert build_editable_ppt_gate({}, validation).issues[0]["code"] == "STRICT_COMPILE_REPORT_MISSING"
    compatible = build_editable_ppt_gate(
        {"editable": "compatible", "forbiddenRasterFallbacks": 0, "issues": []}, validation
    )
    assert compatible.issues[0]["code"] == "EDITABILITY_MODE_NOT_STRICT"
