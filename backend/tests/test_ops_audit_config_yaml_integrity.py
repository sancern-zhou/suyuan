"""ops_audit 配置 YAML 完整性守门。

PyYAML ``safe_load`` 对映射中的重复键不报错、按 last-wins 静默覆盖：
sup_form_profiles.yaml 曾因同名档案重复定义（PM1 月巡查）导致一份档案被
静默遮蔽，规则丢失无从发现。本测试在 compose 节点树上按映射层级检查
重复键，configs/ 下任何 YAML 出现重复即失败；并核对生产加载器读到的
档案数与 YAML 键数一致，防止覆盖类问题再次漏网。
"""

from io import StringIO
from pathlib import Path

import pytest
import yaml

from app.utils.path_config import PROJECT_ROOT

CONFIGS_DIR = PROJECT_ROOT / "backend" / "app" / "services" / "ops_audit" / "configs"


def _collect_duplicate_keys(node, path: str, dups: list[str]) -> None:
    if isinstance(node, yaml.MappingNode):
        seen: dict = {}
        for key_node, _ in node.value:
            key = key_node.value
            line = key_node.start_mark.line + 1
            if key in seen:
                dups.append(f"{path}:{line} 键 {key!r} 与第 {seen[key]} 行重复")
            else:
                seen[key] = line
        for _, value_node in node.value:
            _collect_duplicate_keys(value_node, path, dups)
    elif isinstance(node, yaml.SequenceNode):
        for item in node.value:
            _collect_duplicate_keys(item, path, dups)


def _compose_file(path: Path):
    # compose 必须传文件对象：传路径字符串会被当成 YAML 文本解析成标量节点。
    with path.open("r", encoding="utf-8") as handle:
        return yaml.compose(handle)


def test_detector_flags_synthetic_duplicate() -> None:
    root = yaml.compose(StringIO("a:\n  b: 1\n  b: 2\n"))
    dups: list[str] = []
    _collect_duplicate_keys(root, "synthetic", dups)
    assert len(dups) == 1, dups


def test_configs_dir_has_yaml_files() -> None:
    assert CONFIGS_DIR.is_dir()
    assert any(CONFIGS_DIR.glob("*.yaml"))


@pytest.mark.parametrize(
    "yaml_path",
    sorted(CONFIGS_DIR.glob("*.yaml")),
    ids=lambda p: p.name,
)
def test_no_duplicate_mapping_keys(yaml_path: Path) -> None:
    root = _compose_file(yaml_path)
    assert isinstance(root, yaml.MappingNode), f"{yaml_path.name} 顶层不是映射"
    dups: list[str] = []
    _collect_duplicate_keys(root, yaml_path.name, dups)
    assert not dups, "\n".join(dups)


def test_sup_form_profiles_loaded_count_matches_yaml_keys() -> None:
    """safe_load 读到的档案数必须等于 YAML 中 form_profiles 的键数。

    重复键会让两者不相等（被覆盖的键从字典里消失），构成第二道防线。
    """

    from app.services.ops_audit.config import load_sup_form_profiles

    root = _compose_file(CONFIGS_DIR / "sup_form_profiles.yaml")
    form_profiles_node = next(
        value for key, value in root.value if key.value == "form_profiles"
    )
    yaml_key_count = len(form_profiles_node.value)
    loaded = load_sup_form_profiles()["form_profiles"]
    assert loaded, "生产加载器未读到任何档案"
    assert len(loaded) == yaml_key_count
