# -*- coding: utf-8 -*-
"""Fail-closed parser for Cube schema JS files (data-ops/cube/schema/*.js).

cube/schema/*.js 是查询成员（measures/dimensions）的唯一执行真相：成员不进
schema，Cube 查询必失败。gen_semantic_artifacts.py 用本模块把 schema 解析成
结构化成员清单，再与 registry.yaml 的业务语义 join 成 backend 运行时产物。

解析失败一律抛 SchemaParseError（调用方转 SystemExit），禁止静默空集——
教训来自 validate_registry 旧注释：正则提取在格式变化时会静默得到空集，
让白名单校验退化为永远通过。

只支持本仓库 schema 的固定书写形态（成员名 + `{ type, sql, filters, title }`
字面量），不支持函数体、变量插值成员名等动态写法——出现即报错，由人介入。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Iterator, List, Tuple


class SchemaParseError(RuntimeError):
    """Schema JS 不符合可解析形态——fail-closed，禁止静默降级。"""


def _skip_string(text: str, i: int) -> int:
    """text[i] 是引号（backtick / ' / "）；返回闭合引号之后的下标。"""
    quote = text[i]
    i += 1
    while i < len(text):
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if c == quote:
            return i + 1
        i += 1
    raise SchemaParseError("unterminated string literal")


def _skip_comment(text: str, i: int) -> int:
    """text[i:i+2] 是 // 或 /*；返回注释结束后的下标。"""
    if text[i + 1] == "/":
        nl = text.find("\n", i)
        return len(text) if nl == -1 else nl + 1
    end = text.find("*/", i + 2)
    if end == -1:
        raise SchemaParseError("unterminated block comment")
    return end + 2


def _match_delim(text: str, i: int, open_ch: str, close_ch: str, what: str) -> int:
    """text[i] == open_ch；返回配对 close_ch 的下标（跳过字符串与注释，
    因此 `${...}` 模板内的花括号不会干扰计数）。"""
    depth = 0
    while i < len(text):
        c = text[i]
        if c in "`'\"":
            i = _skip_string(text, i)
            continue
        if c == "/" and i + 1 < len(text) and text[i + 1] in "/*":
            i = _skip_comment(text, i)
            continue
        if c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise SchemaParseError(f"unbalanced {what}")


def _match_brace(text: str, i: int) -> int:
    return _match_delim(text, i, "{", "}", "braces")


def _match_bracket(text: str, i: int) -> int:
    return _match_delim(text, i, "[", "]", "brackets")


def _scan_value(block: str, v: int) -> Tuple[str, int]:
    """读取 block[v:] 起始的一个值，返回 (值文本, 值结束下标)。

    支持 `{...}` / `[...]` 字面量（原样返回）、backtick/引号字符串（返回内容）、
    裸 token（数字/标识符，扫到逗号/换行/右花括号为止）。所有分支都跳过
    字符串与注释，`${CUBE}.col` 之类的模板内容不会被误当成语法。
    """
    c = block[v]
    if c == "{":
        close = _match_brace(block, v)
        return block[v:close + 1], close + 1
    if c == "[":
        close = _match_bracket(block, v)
        return block[v:close + 1], close + 1
    if c in "`'\"":
        after = _skip_string(block, v)
        return block[v + 1:after - 1], after
    j, n = v, len(block)
    while j < n:
        ch = block[j]
        if ch in "`'\"":
            j = _skip_string(block, j)
            continue
        if ch == "/" and j + 1 < n and block[j + 1] in "/*":
            j = _skip_comment(block, j)
            continue
        if ch in ",\r\n}":
            break
        j += 1
    return block[v:j].strip(), j


def _iter_entries(block: str) -> Iterator[Tuple[str, str, int, int]]:
    """按书写顺序产出 (key, value, value_start, value_end_after)。

    只识别块内顶层键；字符串与注释内容不产生键。
    """
    i, n = 0, len(block)
    while i < n:
        c = block[i]
        if c in "`'\"":
            i = _skip_string(block, i)
            continue
        if c == "/" and i + 1 < n and block[i + 1] in "/*":
            i = _skip_comment(block, i)
            continue
        if c.isalpha() or c in "_$":
            j = i
            while j < n and (block[j].isalnum() or block[j] in "_$"):
                j += 1
            key = block[i:j]
            k = j
            while k < n and block[k] in " \t\r\n":
                k += 1
            if k >= n or block[k] != ":":
                i = j
                continue
            v = k + 1
            while v < n and block[v] in " \t\r\n":
                v += 1
            if v >= n:
                raise SchemaParseError(f"key '{key}' has no value")
            value, after = _scan_value(block, v)
            yield key, value, v, after
            i = after
            continue
        i += 1


def _require_block(entries: List[Tuple[str, str, int, int]], key: str, where: str) -> str:
    for name, value, _s, _e in entries:
        if name == key:
            if not value.startswith("{"):
                raise SchemaParseError(f"{where}: '{key}' must be a {{...}} block")
            return value
    raise SchemaParseError(f"{where}: missing '{key}' block")


def parse_schema_text(text: str, source: str) -> Dict[str, Any]:
    """解析单个 schema 文件文本 → {cube: {"measures": {name: {"title": ...}},
    "dimensions": {...}}}（成员保持文件书写顺序）。"""
    decls = list(re.finditer(r"cube\(\s*`([A-Za-z0-9_]+)`", text))
    if not decls:
        raise SchemaParseError(f"{source}: no cube(`Name`) declaration")
    if len(decls) > 1:
        raise SchemaParseError(f"{source}: multiple cube declarations in one file")
    cube = decls[0].group(1)
    body_open = text.find("{", decls[0].end())
    if body_open == -1:
        raise SchemaParseError(f"{source}: cube body not found")
    body_close = _match_brace(text, body_open)
    body = text[body_open + 1:body_close]

    top = list(_iter_entries(body))
    measures_block = _require_block(top, "measures", f"{source}:{cube}")
    dimensions_entries = [e for e in top if e[0] == "dimensions"]
    if len(dimensions_entries) > 1:
        raise SchemaParseError(f"{source}:{cube}: duplicate 'dimensions' block")

    def parse_members(block: str, kind: str) -> Dict[str, Dict[str, str]]:
        members: Dict[str, Dict[str, str]] = {}
        for name, value, _s, _e in _iter_entries(block):
            if not value.startswith("{"):
                raise SchemaParseError(
                    f"{source}:{cube}.{kind}.{name}: member must be a {{...}} literal")
            props = {k: v for k, v, _vs, _ve in _iter_entries(value[1:-1])}
            title = props.get("title") or name
            members[name] = {"title": title}
        return members

    parsed: Dict[str, Any] = {
        "measures": parse_members(measures_block, "measures"),
        "dimensions": {},
    }
    if dimensions_entries:
        parsed["dimensions"] = parse_members(dimensions_entries[0][1], "dimensions")
    if not parsed["measures"]:
        raise SchemaParseError(f"{source}:{cube}: no measures parsed")
    return {cube: parsed}


def parse_schema_dir(schema_dir: Path) -> Dict[str, Dict[str, Any]]:
    """解析目录下全部 *.js（按文件名序）；同名 cube 重复声明即报错。"""
    merged: Dict[str, Dict[str, Any]] = {}
    for path in sorted(schema_dir.glob("*.js")):
        parsed = parse_schema_text(path.read_text(encoding="utf-8"), path.name)
        for cube, spec in parsed.items():
            if cube in merged:
                raise SchemaParseError(f"{path.name}: duplicate cube '{cube}'")
            merged[cube] = spec
    if not merged:
        raise SchemaParseError(f"{schema_dir}: no cube schema parsed")
    return merged
