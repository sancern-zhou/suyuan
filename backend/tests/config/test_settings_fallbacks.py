from config.settings import Settings


def test_invalid_social_yaml_uses_non_recursive_defaults(tmp_path):
    config_path = tmp_path / "social_config.yaml"
    config_path.write_text("channels: [", encoding="utf-8")

    settings = Settings(social_config_path=str(config_path))

    assert settings.load_social_config() == settings._default_social_config()
