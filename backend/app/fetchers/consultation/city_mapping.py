# -*- coding: utf-8 -*-
"""Guangdong city code/name helpers for consultation supplement outputs."""

from __future__ import annotations

import re
from typing import Any, Optional, Tuple


CITY_CODE_TO_NAME = {
    "440100": "广州",
    "440200": "韶关",
    "440300": "深圳",
    "440400": "珠海",
    "440500": "汕头",
    "440600": "佛山",
    "440700": "江门",
    "440800": "湛江",
    "440900": "茂名",
    "441200": "肇庆",
    "441300": "惠州",
    "441400": "梅州",
    "441500": "汕尾",
    "441600": "河源",
    "441700": "阳江",
    "441800": "清远",
    "441900": "东莞",
    "442000": "中山",
    "445100": "潮州",
    "445200": "揭阳",
    "445300": "云浮",
}

CITY_NAME_TO_CODE = {
    **{name: code for code, name in CITY_CODE_TO_NAME.items()},
    **{f"{name}市": code for code, name in CITY_CODE_TO_NAME.items()},
}


def normalize_city_identity(value: Any) -> Tuple[str, str]:
    """Return `(city_name, city_code)` from a city name or Guangdong city code."""
    raw = "" if value is None else str(value).strip()
    if not raw:
        return "", ""

    code = _extract_city_code(raw)
    if code:
        return CITY_CODE_TO_NAME.get(code, raw), code

    compact = raw[:-1] if raw.endswith("市") else raw
    mapped_code = CITY_NAME_TO_CODE.get(raw) or CITY_NAME_TO_CODE.get(compact)
    if mapped_code:
        return CITY_CODE_TO_NAME[mapped_code], mapped_code

    return raw, ""


def _extract_city_code(value: str) -> Optional[str]:
    if re.fullmatch(r"\d{6}(?:\.0)?", value):
        return value.split(".", 1)[0]
    return None
