from app.services.ops_audit.semantic import ocr_adapter


def test_extract_attachment_text_returns_error_for_missing_file():
    result = ocr_adapter.extract_attachment_text("does-not-exist.png")

    assert result["status"] == "error"
    assert result["confidence"] == 0.0
    assert "不存在" in result["error"]


def test_extract_attachment_text_uses_bailian_anthropic(tmp_path, monkeypatch):
    image_path = tmp_path / "sample.png"
    image_path.write_bytes(b"fake-image-bytes")
    monkeypatch.setenv("BAILIAN_API_KEY", "test-key-id")
    monkeypatch.setattr(ocr_adapter.settings, "bailian_model", "qwen3.8-max-preview")
    monkeypatch.setenv("BAILIAN_BASE_URL", "https://bailian.example/apps/anthropic")

    captured = {}

    def _fake_call(**kwargs):
        captured["kwargs"] = kwargs
        return "第一行\n第二行", {"usage": {"output_tokens": 12}}

    monkeypatch.setattr(ocr_adapter, "call_bailian_vision_sync", _fake_call)

    result = ocr_adapter.extract_attachment_text(str(image_path))

    assert result["status"] == "success"
    assert result["provider"] == "qwen3.8-max-preview"
    assert result["mode"] == "general"
    assert result["text"] == "第一行\n第二行"
    assert result["confidence"] == 0.8
    assert captured["kwargs"]["model"] == "qwen3.8-max-preview"
    assert captured["kwargs"]["base_url"] == "https://bailian.example/apps/anthropic"
    assert captured["kwargs"]["image_url"].startswith("data:image/png;base64,")


def test_extract_attachment_text_uses_one_bailian_model_for_all_modes(tmp_path, monkeypatch):
    image_path = tmp_path / "sample.png"
    image_path.write_bytes(b"fake-image-bytes")
    monkeypatch.setenv("BAILIAN_API_KEY", "test-key-id")
    monkeypatch.setattr(ocr_adapter.settings, "bailian_model", "qwen3.8-max-preview")

    captured_actions = []

    def _fake_call(**kwargs):
        captured_actions.append(kwargs["model"])
        return "示例", {"content": [{"type": "text", "text": "示例"}]}

    monkeypatch.setattr(ocr_adapter, "call_bailian_vision_sync", _fake_call)

    document_result = ocr_adapter.extract_attachment_text(str(image_path), provider="document")
    table_result = ocr_adapter.extract_attachment_text(str(image_path), provider="table")

    assert document_result["provider"] == "qwen3.8-max-preview"
    assert table_result["provider"] == "qwen3.8-max-preview"
    assert document_result["mode"] == "document"
    assert table_result["mode"] == "table"
    assert captured_actions == ["qwen3.8-max-preview", "qwen3.8-max-preview"]
