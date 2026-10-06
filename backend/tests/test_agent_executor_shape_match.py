"""executor 形状匹配：归一化精确匹配，禁止前后缀模糊匹配。"""

from app.agent.core.executor import _match_result_shape


def _shape(row_count: int) -> dict:
    return {"columns": [{"name": "a", "type": "int"}], "row_count": row_count, "source": "inferred"}


def test_rejects_suffix_collision_between_filenames():
    shapes = {"1.csv": _shape(1)}
    assert _match_result_shape(shapes, "xx11.csv") is None


def test_prefers_exact_raw_key():
    shapes = {"1.csv": _shape(1), "xx11.csv": _shape(11)}
    assert _match_result_shape(shapes, "xx11.csv") == _shape(11)


def test_matches_relative_key_against_absolute_path(monkeypatch, tmp_path):
    import app.utils.path_config as path_config

    monkeypatch.setattr(path_config, "PROJECT_ROOT", tmp_path)
    target = tmp_path / "backend" / "registry" / "sessions" / "s1" / "result.json"
    shapes = {"backend/registry/sessions/s1/result.json": _shape(3)}
    assert _match_result_shape(shapes, str(target)) == _shape(3)


def test_ignores_non_dict_shapes():
    assert _match_result_shape({"b.json": "not-a-shape"}, "b.json") is None
    assert _match_result_shape(None, "b.json") is None
