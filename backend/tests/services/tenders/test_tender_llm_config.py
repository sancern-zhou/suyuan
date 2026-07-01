from app.services.tenders.llm import OpenAICompatibleTenderLLMClient


def test_tender_llm_uses_configured_glm_provider_when_selected(monkeypatch):
    for name in [
        "TENDER_LLM_API_KEY",
        "TENDER_LLM_BASE_URL",
        "TENDER_LLM_MODEL",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_MODEL",
        "DASHSCOPE_API_KEY",
        "DASHSCOPE_MODEL",
        "QWEN_API_KEY",
        "QWEN_MODEL",
    ]:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "glm")
    monkeypatch.setenv("GLM_API_KEY", "glm-valid-key")
    monkeypatch.setenv("GLM_BASE_URL", "https://open.bigmodel.cn/api/coding/paas/v4")
    monkeypatch.setenv("GLM_MODEL", "glm-4.7")

    client = OpenAICompatibleTenderLLMClient()

    assert client.api_key == "glm-valid-key"
    assert client.base_url == "https://open.bigmodel.cn/api/coding/paas/v4"
    assert client.model == "glm-4.7"
