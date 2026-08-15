from app.tools.utility.execute_python_tool import ExecutePythonTool


def test_execute_python_attach_resume_context_from_known_outputs(tmp_path):
    output_file = tmp_path / "report.docx"
    output_file.write_bytes(b"docx")
    chart_file = tmp_path / "chart.png"
    chart_file.write_bytes(b"png")
    data_file = tmp_path / "python-result.json"
    data_file.write_text("[]", encoding="utf-8")

    result = {
        "success": True,
        "data": {
            "files": [str(output_file)],
            "file_path": str(output_file),
            "data_file_paths": [str(data_file)],
        },
        "visuals": [
            {
                "id": "chart_1",
                "type": "image",
                "title": "图表",
                "data": {
                    "url": "/api/image/chart_1",
                    "local_path": str(chart_file),
                    "source_file_path": str(chart_file),
                },
            }
        ],
    }

    ExecutePythonTool()._attach_resume_context(result)

    assert result["refs"] == {
        "files": [
            {
                "path": str(output_file),
                "type": "document",
                "format": "docx",
                "size": 4,
                "usage": "generated_file",
                "preferred_for": ["read_file", "list_session_resources"],
            }
        ],
        "data": [
            {
                "file_path": str(data_file),
                "usage": "generated",
            }
        ],
        "visuals": [
            {
                "id": "chart_1",
                "type": "image",
                "title": "图表",
                "image_url": "/api/image/chart_1",
                "local_path": str(chart_file),
                "file_path": str(chart_file),
                "tool_path": str(chart_file),
            }
        ],
    }
    assert result["llm_resume"] == {
        "generated_files": [str(output_file)],
        "auto_published": True,
        "publish_session_file_required": False,
        "tool_hint": (
            "Generated files have already been published to the unified session resource catalog. "
            "Do not call publish_session_file and do not construct a sessions/... path. "
            "Reuse the returned file_path exactly, or use list_session_resources to inspect the resource IDs."
        ),
        "file_paths": [str(data_file)],
    }
