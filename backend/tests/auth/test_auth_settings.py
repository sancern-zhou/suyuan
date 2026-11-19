import pytest
from pydantic import ValidationError

from config.settings import Settings


@pytest.fixture(autouse=True)
def _isolate_settings_environment(monkeypatch):
    """Settings(_env_file=None) 仍会读取 os.environ。

    其他模块导入时 load_dotenv() 会把 backend/.env 灌进进程环境，
    这里清空与配置字段同名（含 validation_alias）的变量，
    保证断言的是代码默认值而不是部署机的 .env。
    """
    names = set()
    for name, field in Settings.model_fields.items():
        names.add(name.upper())
        alias = field.validation_alias
        choices = getattr(alias, "choices", None)
        if choices is None and isinstance(alias, str):
            choices = (alias,)
        for choice in choices or ():
            if isinstance(choice, str):
                names.add(choice.upper())
    for name in names:
        monkeypatch.delenv(name, raising=False)
    yield


def test_company_auth_contract_defaults(monkeypatch):
    monkeypatch.delenv("AUTH_MODE", raising=False)
    value = Settings(_env_file=None)

    assert value.auth_mode == "company"
    assert value.auth_sys_code == "SUYUAN"
    assert value.auth_platform_sys_code == "JCXT"
    assert value.gateway_api_prefix == "/api/suyuan"
    assert value.auth_identity_cache_key_prefix == "suyuan:auth:"
    assert value.nacos_namespace == "normcraft-ai"
    assert value.nacos_group == "DEFAULT_GROUP"
    assert value.nacos_service_name == "suyuan-agent"
    assert value.nacos_register_enabled is True


def test_project_environment_selects_deployment(monkeypatch):
    monkeypatch.setenv("PROJECT", "jiyuan")

    value = Settings(_env_file=None)

    assert value.project_id == "jiyuan"


def test_mock_authentication_has_no_redundant_enable_switch():
    value = Settings(_env_file=None, environment="development", auth_mode="mock")

    assert not hasattr(value, "auth_mock_enabled")


def test_auth_list_properties_trim_and_deduplicate_values():
    value = Settings(
        _env_file=None,
        auth_admin_role_codes=" admin,SUYUAN_ADMIN,admin ",
        trusted_gateway_networks="127.0.0.1/32, 10.10.204.0/24,127.0.0.1/32",
        nacos_server_addresses="http://nacos-a:8848, http://nacos-b:8848",
    )

    assert value.auth_admin_role_codes_set == {"admin", "SUYUAN_ADMIN"}
    assert value.trusted_gateway_networks_list == ["127.0.0.1/32", "10.10.204.0/24"]
    assert value.nacos_server_addresses_list == [
        "http://nacos-a:8848",
        "http://nacos-b:8848",
    ]


def test_production_rejects_mock_authentication():
    with pytest.raises(ValidationError, match="mock authentication"):
        Settings(
            _env_file=None,
            environment="production",
            auth_mode="mock",
            auth_service_url="http://platform-gateway/api",
            share_signing_secret="share-secret",
        )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"nacos_register_enabled": False}, "Nacos registration"),
        ({"auth_service_url": ""}, "AUTH_SERVICE_URL"),
        ({"share_signing_secret": ""}, "share-signing secret"),
        ({"trusted_gateway_networks": "0.0.0.0/0"}, "trusted gateway network"),
    ],
)
def test_production_fails_closed_for_insecure_configuration(overrides, message):
    values = {
        "_env_file": None,
        "environment": "production",
        "auth_mode": "company",
        "auth_service_url": "http://platform-gateway/api",
        "share_signing_secret": "share-secret",
        "nacos_register_enabled": True,
        "trusted_gateway_networks": "10.10.204.0/24",
    }
    values.update(overrides)

    with pytest.raises(ValidationError, match=message):
        Settings(**values)


def test_valid_production_configuration_is_accepted():
    value = Settings(
        _env_file=None,
        environment="production",
        auth_mode="company",
        auth_service_url="http://platform-gateway/api",
        share_signing_secret="share-secret",
        trusted_gateway_networks="10.10.204.0/24",
    )

    assert value.environment == "production"
