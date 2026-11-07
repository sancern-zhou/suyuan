"""Generate the xuchang semantic catalog artifact for the query tool.

成员真相在 cube/schema/*.js（执行层），中文标题/口径语义在 semantic/registry.yaml
（人工维护层）。本生成器把两者合成单一 catalog.generated.json，写入工具目录，
供 xuchang_cube_metrics 模块导入期 fail-closed 加载。

- 成员集必须镜像 JS：多一个/少一个成员都是漂移（fail-closed, SystemExit）
- registry 中不存在的成员标题回落为成员名本身
- --check 逐字节比对已提交产物，漂移即非零退出（接入提交前自检）
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
SCHEMA_DIR = HERE.parent / "cube" / "schema"
REGISTRY = HERE / "registry.yaml"
# 生成器写入工具目录（与 result_contract.txt 同模式），工具模块导入期加载。
TARGET = Path(__file__).resolve().parents[4] / "backend/app/tools/query/xuchang_cube_metrics/catalog.generated.json"

CUBE_HEADER = re.compile(r"cube\(\s*`([A-Za-z0-9_]+)`\s*,\s*\{")
MEMBER_KEY = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*\{", re.M)


def _match_brace(text: str, open_index: int) -> int:
    """返回与 open_index 处 '{' 匹配的 '}' 索引；感知反引号/引号字符串与注释。"""
    assert text[open_index] == "{"
    depth, i, n = 0, open_index, len(text)
    while i < n:
        char = text[i]
        if char in "`'\"":
            quote = char
            i += 1
            while i < n and text[i] != quote:
                i += 2 if text[i] == "\\" else 1
        elif char == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise ValueError("unbalanced braces")


def _section(body: str, key: str) -> str:
    """提取 cube body 内 `key: { ... }` 段内容；缺失返回空串。"""
    match = re.search(rf"(?:^|\n)\s*{key}\s*:\s*\{{", body)
    if not match:
        return ""
    open_index = body.index("{", match.start())
    return body[open_index + 1 : _match_brace(body, open_index)]


def parse_schemas() -> dict[str, dict[str, list[str]]]:
    """解析全部 schema/*.js 的成员名（执行真相）。结构异常即失败。"""
    cubes: dict[str, dict[str, list[str]]] = {}
    for js_path in sorted(SCHEMA_DIR.glob("*.js")):
        text = js_path.read_text(encoding="utf-8")
        for match in CUBE_HEADER.finditer(text):
            name = match.group(1)
            open_index = text.index("{", match.start())
            body = text[open_index + 1 : _match_brace(text, open_index)]
            measures = MEMBER_KEY.findall(_section(body, "measures"))
            dimensions = MEMBER_KEY.findall(_section(body, "dimensions"))
            if not measures:
                raise SystemExit(f"{js_path.name}: cube {name} 缺 measures 成员（解析失败或 schema 损坏）")
            if name in cubes:
                raise SystemExit(f"{js_path.name}: cube {name} 重复定义")
            cubes[name] = {"measures": measures, "dimensions": dimensions}
    if not cubes:
        raise SystemExit(f"{SCHEMA_DIR} 未解析出任何 cube")
    return cubes


def build() -> dict:
    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}
    reg_cubes = registry.get("cubes") or {}
    js_cubes = parse_schemas()

    drifted = sorted(set(js_cubes) ^ set(reg_cubes))
    if drifted:
        raise SystemExit(
            f"registry.yaml 与 cube/schema/*.js 的 Cube 集合不一致: {drifted}；"
            "成员真相在 schema/*.js，请同步 registry.yaml"
        )

    result = {}
    for cube in sorted(js_cubes):
        reg_entry = reg_cubes.get(cube) or {}
        reg_measures = reg_entry.get("measures") or {}
        stale = sorted(set(reg_measures) - set(js_cubes[cube]["measures"]))
        if stale:
            raise SystemExit(f"registry.yaml 中 {cube} 存在 schema 没有的成员: {stale}")

        def titled(member: str) -> dict[str, str]:
            title = str((reg_measures.get(member) or {}).get("name") or member)
            return {"name": member, "title": title}

        result[cube] = {
            "measures": [titled(m) for m in js_cubes[cube]["measures"]],
            "dimensions": [titled(d) for d in js_cubes[cube]["dimensions"]],
        }
    return {
        "version": registry.get("version", 0),
        "project": "xuchang",
        "generated_from": ["cube/schema/*.js", "semantic/registry.yaml"],
        "cubes": result,
    }


def main() -> int:
    content = (
        json.dumps(build(), ensure_ascii=False, indent=2, sort_keys=False)
        + "\n"
    )
    if "--check" in sys.argv:
        if not TARGET.exists() or TARGET.read_text(encoding="utf-8") != content:
            print("XUCHANG_CATALOG_ARTIFACT_DRIFT")
            return 1
        print(f"XUCHANG_CATALOG_ARTIFACT_OK cubes={len(build()['cubes'])}")
        return 0
    TARGET.write_text(content, encoding="utf-8", newline="\n")
    print(f"written: {TARGET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
