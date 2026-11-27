"""百度地图 Web 服务 API 服务校验（SN）签名。

官方算法：对 ``路径?参数串``（参数按 key 字典序排列、值为原文，sn 不参与）
先做一次 ``quote(safe=保留字符集)`` 编码，拼接 SK 后整体再做一次
``quote_plus`` 编码，最后取 MD5 十六进制。GET 请求的 sn 固定追加在参数末尾。
"""
from __future__ import annotations

import hashlib
from collections.abc import Mapping
from urllib.parse import quote, quote_plus

# 官方文档指定的保留字符集，quote 编码时不转换
SAFE_CHARS = "/:=&?#+!$,;'@()*[]"


def calc_sn(path: str, params: Mapping[str, object], sk: str) -> str:
    """按官方 SN 算法计算请求签名。"""
    query_str = path + "?" + "&".join(f"{key}={params[key]}" for key in sorted(params))
    encoded = quote(query_str, safe=SAFE_CHARS)
    return hashlib.md5(quote_plus(encoded + sk).encode("utf-8")).hexdigest()


def build_signed_url(
    base_url: str,
    path: str,
    params: Mapping[str, object],
    ak: str,
    sk: str,
) -> str:
    """构造带 ak 与 sn 的完整请求 URL。

    参数值按官方保留字符集做单次百分号编码（中文编码一次），sn 固定在最后。
    """
    signed = {**params, "ak": ak}
    sn = calc_sn(path, signed, sk)
    query = "&".join(
        f"{key}={quote(str(signed[key]), safe=SAFE_CHARS)}" for key in sorted(signed)
    )
    return f"{base_url}{path}?{query}&sn={sn}"
