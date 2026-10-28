"""空气质量信息联网系统（旧云平台）客户端。

http://117.159.53.11:60601（政府侧部署）。许昌 76 个区县乡镇站的
5 分钟/小时/日数据仍由该平台实时发布，是 Crawler MySQL TownStationData
2026-10-21 起停更后的替代采集源。

登录协议（2026-10-27 实测）：
- GET  /prod-api/auth/key 返回 RSA 公钥（X.509 DER，Base64 单行）；
- GET  /prod-api/code 返回 {uuid, img}，img 为算术验证码 JPEG，形如
  "5+1=?"，运算符含 + - * /（除法保证整除），一次性消费、答错作废；
- 密码字段为 RSA(PKCS#1 v1.5) 加密的 {"username","password"} JSON 整体
  （前端 encryptedData 实现），不是明文也不是密码本身的加密；
- POST /prod-api/auth/login {username, code, uuid, password} →
  {code:200, data:{access_token, expires_in}}，token 有效期 12 小时。

验证码识别：图片扭曲严重，ddddocr 实测几乎不可用（2/12 且答案错误）；
改用 GLM 网关 glm-4.6v 视觉模型（复用 settings.glm_* 配置，thinking
关闭），单次识别实测 4/5，验证码错误时换图重试即可。

业务接口前缀 /prod-api/subsystem/ssair：
- /airNetwork/page?tstype=4 站点目录（76 站，含在线状态与最新值）；
- /airData/page 三粒度统一查询（tstype=4&timeStep=1|2|3&type=1），
  5 分钟数据（timeStep=1）限查 3 天以内窗口。
"""

from __future__ import annotations

import base64
import json
import re
import time
from datetime import datetime
from typing import Any

import requests
import structlog
from Crypto.Cipher import PKCS1_v1_5
from Crypto.PublicKey import RSA

from config.settings import settings

logger = structlog.get_logger()

TOKEN_REFRESH_MARGIN_SECONDS = 600  # 提前 10 分钟刷新，避免临界过期
MAX_PAGES = 50  # 分页保险丝：2000/页 × 50 足够 3 天 × 76 站

# 算式识别：数字 运算符 数字（容忍 OCR 把等号/问号读丢）
_ARITHMETIC = re.compile(r"(\d+)\s*([+\-x×*/])\s*(\d+)")


def eval_captcha_expression(text: str | None) -> str | None:
    """从 OCR 文本中解析算式并求值；解析失败返回 None。"""
    match = _ARITHMETIC.search(text or "")
    if not match:
        return None
    left, operator, right = int(match.group(1)), match.group(2), int(match.group(3))
    try:
        if operator == "+":
            return str(left + right)
        if operator == "-":
            return str(left - right)
        if operator in ("x", "×", "*"):
            return str(left * right)
        if operator == "/":
            return str(left // right) if right else None
    except Exception:  # noqa: BLE001 - 除零等异常按解析失败处理
        return None
    return None


class TownCloudLoginError(RuntimeError):
    """登录失败（验证码多次识别失败或凭据被拒）。"""


class TownCloudClient:
    """空气质量信息联网系统会话与数据查询。"""

    def __init__(
        self,
        base_url: str | None = None,
        username: str | None = None,
        password: str | None = None,
        timeout: float | None = None,
        login_retries: int | None = None,
    ) -> None:
        self.base_url = (base_url or settings.town_cloud_api_base_url).rstrip("/")
        self.username = username or settings.town_cloud_username
        self.password = password or settings.town_cloud_password
        self.timeout = timeout or settings.town_cloud_timeout_seconds
        self.login_retries = login_retries or settings.town_cloud_login_retries
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    # ---- 验证码识别 --------------------------------------------------------
    def _read_captcha_with_vision(self, image_bytes: bytes) -> str | None:
        """调用 GLM 视觉模型识别算术验证码，返回求值结果；失败返回 None。"""
        api_key = settings.glm_api_key
        base_url = (settings.glm_base_url or "").rstrip("/")
        if not api_key or not base_url:
            raise TownCloudLoginError(
                "未配置 GLM_API_KEY / GLM_BASE_URL，无法识别云平台验证码"
            )
        image_b64 = base64.b64encode(image_bytes).decode()
        try:
            resp = requests.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "glm-4.6v",
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                                },
                                {
                                    "type": "text",
                                    "text": "识别图中的算术验证码，只输出完整算式本身（例如 5+1=?），不要思考过程，不要其他文字。",
                                },
                            ],
                        }
                    ],
                    "max_tokens": 1024,
                    "temperature": 0,
                    "thinking": {"type": "disabled"},
                },
                timeout=60,
            )
            resp.raise_for_status()
            choice = (resp.json().get("choices") or [{}])[0]
            text = (choice.get("message") or {}).get("content") or ""
        except Exception as exc:  # noqa: BLE001 - 视觉服务异常按本轮识别失败处理
            logger.warning("town_cloud_vision_captcha_failed", error=str(exc))
            return None
        return eval_captcha_expression(text)

    # ---- 登录 --------------------------------------------------------------
    def _rsa_encrypt_credentials(self, public_key_der_b64: str) -> str:
        credentials = json_dumps_credentials(self.username, self.password)
        key = RSA.import_key(base64.b64decode(public_key_der_b64))
        cipher = PKCS1_v1_5.new(key)
        return base64.b64encode(cipher.encrypt(credentials.encode("utf-8"))).decode()

    def login(self) -> str:
        """登录并缓存 access_token；验证码识别失败自动换图重试。"""
        if not self.username or not self.password:
            raise TownCloudLoginError(
                "未配置 TOWN_CLOUD_USERNAME / TOWN_CLOUD_PASSWORD，无法登录云平台"
            )
        key_resp = requests.get(
            f"{self.base_url}/prod-api/auth/key", timeout=self.timeout
        )
        key_resp.raise_for_status()
        key_payload = key_resp.json()
        if key_payload.get("code") != 200 or not key_payload.get("data"):
            raise TownCloudLoginError(f"获取 RSA 公钥失败: {key_payload}")
        encrypted = self._rsa_encrypt_credentials(key_payload["data"])

        last_reason = ""
        for attempt in range(1, self.login_retries + 1):
            captcha_resp = requests.get(
                f"{self.base_url}/prod-api/code", timeout=self.timeout
            )
            captcha_resp.raise_for_status()
            captcha = captcha_resp.json()
            uuid, image_b64 = captcha.get("uuid"), captcha.get("img") or ""
            code = self._read_captcha_with_vision(base64.b64decode(image_b64))
            if code is None:
                last_reason = "验证码识别失败"
                logger.warning("town_cloud_captcha_retry", attempt=attempt)
                continue
            result = requests.post(
                f"{self.base_url}/prod-api/auth/login",
                json={
                    "username": self.username,
                    "code": code,
                    "uuid": uuid,
                    "password": encrypted,
                },
                timeout=self.timeout,
            ).json()
            if result.get("code") == 200 and (result.get("data") or {}).get("access_token"):
                data = result["data"]
                self._token = data["access_token"]
                self._token_expires_at = (
                    time.time() + int(data.get("expires_in") or 43200)
                )
                logger.info(
                    "town_cloud_login_ok",
                    attempt=attempt,
                    expires_in=data.get("expires_in"),
                )
                return self._token
            last_reason = str(result.get("msg") or result)
            logger.warning(
                "town_cloud_login_retry", attempt=attempt, reason=last_reason
            )
        raise TownCloudLoginError(
            f"云平台登录失败（已重试 {self.login_retries} 次）: {last_reason}"
        )

    def _ensure_token(self) -> str:
        if (
            self._token is None
            or time.time() >= self._token_expires_at - TOKEN_REFRESH_MARGIN_SECONDS
        ):
            self.login()
        return self._token  # type: ignore[return-value]

    # ---- 数据查询 ----------------------------------------------------------
    def _get_json(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        """带鉴权 GET；token 失效（HTTP 401 或 code 401）时重登一次。"""
        for retried in (False, True):
            resp = requests.get(
                f"{self.base_url}/prod-api{path}",
                params=params,
                headers={"Authorization": f"Bearer {self._ensure_token()}"},
                timeout=self.timeout,
            )
            if resp.status_code == 401 and not retried:
                self._token = None
                continue
            resp.raise_for_status()
            payload = resp.json()
            if payload.get("code") == 401 and not retried:
                self._token = None
                continue
            return payload
        return payload

    def fetch_station_directory(self) -> list[dict[str, Any]]:
        """拉取乡镇站目录（airNetwork/page，含 tsno/站名/县区/在线状态）。

        airData/page 的数据行不带 tsno（只有站名与 countyId），落库前
        需要用本目录按 (countyId, name) 关联出站码。
        """
        rows: list[dict[str, Any]] = []
        page = 1
        while True:
            payload = self._get_json(
                "/subsystem/ssair/airNetwork/page",
                {"pageNum": page, "pageSize": 500, "tstype": "4"},
            )
            if payload.get("code") != 200:
                raise RuntimeError(f"airNetwork/page 查询失败: {payload}")
            batch = payload.get("rows") or []
            rows.extend(batch)
            total = int(payload.get("total") or 0)
            if not batch or len(rows) >= total:
                break
            page += 1
            if page > MAX_PAGES:
                logger.warning(
                    "town_cloud_directory_too_many_pages",
                    total=total,
                    collected=len(rows),
                )
                break
        return rows

    def fetch_air_data(
        self,
        start: datetime,
        end: datetime,
        *,
        time_step: int = 1,
        page_size: int = 2000,
    ) -> list[dict[str, Any]]:
        """拉取时间窗口内全部乡镇站（tstype=4）数据行。

        timeStep: 1=5分钟（窗口不得超过 3 天，平台限制）、2=小时、3=日。
        """
        rows: list[dict[str, Any]] = []
        page = 1
        while True:
            payload = self._get_json(
                "/subsystem/ssair/airData/page",
                {
                    "pageNum": page,
                    "pageSize": page_size,
                    "tstype": "4",
                    "timeStep": str(time_step),
                    "type": "1",
                    "isAudit": "0",
                    "collectionTimeBegin": start.strftime("%Y-%m-%d %H:%M:%S"),
                    "collectionTimeEnd": end.strftime("%Y-%m-%d %H:%M:%S"),
                },
            )
            if payload.get("code") != 200:
                raise RuntimeError(f"airData/page 查询失败: {payload}")
            batch = payload.get("rows") or []
            rows.extend(batch)
            total = int(payload.get("total") or 0)
            if not batch or len(rows) >= total:
                break
            page += 1
            if page > MAX_PAGES:
                logger.warning(
                    "town_cloud_too_many_pages", total=total, collected=len(rows)
                )
                break
        return rows


def json_dumps_credentials(username: str, password: str) -> str:
    """复现前端 RSA 加密前的 JSON 序列化（{"username":...,"password":...}）。"""
    return json.dumps(
        {"username": username, "password": password},
        ensure_ascii=False,
        separators=(",", ":"),
    )
