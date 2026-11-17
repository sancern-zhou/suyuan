import pytest

from app.services.llm_service import LLMService, _parse_extra_headers
from config.settings import settings


def test_parse_extra_headers_valid_json():
    assert _parse_extra_headers('{"jcmp-token":"abc","X-Trace":"1"}') == {
        "jcmp-token": "abc",
        "X-Trace": "1",
    }


def test_parse_extra_headers_empty_and_blank():
    assert _parse_extra_headers("") == {}
    assert _parse_extra_headers("   ") == {}


def test_parse_extra_headers_invalid_json_returns_empty():
    assert _parse_extra_headers("jcmp-token=abc") == {}


def test_parse_extra_headers_non_object_returns_empty():
    assert _parse_extra_headers('["jcmp-token"]') == {}


def test_parse_extra_headers_skips_none_values():
    assert _parse_extra_headers('{"a": null, "b": "keep"}') == {"b": "keep"}


def test_get_request_config_appends_extra_headers(monkeypatch):
    monkeypatch.setattr(
        settings, "llm_extra_headers", '{"jcmp-token":"5804"}', raising=False
    )
    service = object.__new__(LLMService)
    service.provider = "openai"
    service.base_url = "http://10.10.68.237:41080/large-model/api/v1"
    service.api_key = "sk-test"

    url, headers = service._get_request_config()

    assert url == "http://10.10.68.237:41080/large-model/api/v1/chat/completions"
    assert headers["Authorization"] == "Bearer sk-test"
    assert headers["jcmp-token"] == "5804"


def test_get_request_config_without_extra_headers(monkeypatch):
    monkeypatch.setattr(settings, "llm_extra_headers", "", raising=False)
    service = object.__new__(LLMService)
    service.provider = "openai"
    service.base_url = "http://example.internal/api/v1"
    service.api_key = "sk-test"

    url, headers = service._get_request_config()

    assert "jcmp-token" not in headers
    assert headers["Authorization"] == "Bearer sk-test"
