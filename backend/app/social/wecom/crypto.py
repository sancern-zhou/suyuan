"""企业微信回调消息加解密与验签（WXBizMsgCrypt 协议的独立实现）。

协议要点（企业微信开发者文档-加解密方案）：
- EncodingAESKey 为 43 位字符串，Base64 解码（补 "="）得 32 字节 AES key；
- AES-256-CBC，IV = key 前 16 字节，PKCS7 填充（块 32 字节）；
- 明文结构 = random(16B) + msg_len(4B 网络字节序) + msg + receiveid；
- 签名 = sha1(sort(token, timestamp, nonce, encrypt密文))。

只用 pycryptodome，不引入官方示例代码。
"""

from __future__ import annotations

import base64
import hashlib
import os
import struct

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

_BLOCK_BYTES = 32  # 企业微信约定 PKCS7 填充块为 32 字节


class WecomCryptoError(ValueError):
    """Raised on signature mismatch or malformed ciphertext."""


class WecomCrypto:
    def __init__(self, token: str, encoding_aes_key: str, *, receive_id: str = ""):
        if len(encoding_aes_key) != 43:
            raise WecomCryptoError("encoding_aes_key must be 43 chars")
        self.token = token
        self.receive_id = receive_id
        self.key = base64.b64decode(encoding_aes_key + "=")

    def signature(self, timestamp: str, nonce: str, encrypt: str) -> str:
        raw = "".join(sorted([self.token, timestamp, nonce, encrypt]))
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def verify(self, signature: str, timestamp: str, nonce: str, encrypt: str) -> bool:
        if not signature or not encrypt:
            return False
        import hmac as _hmac

        return _hmac.compare_digest(
            signature, self.signature(timestamp, nonce, encrypt)
        )

    def decrypt(self, encrypt: str) -> str:
        try:
            cipher = AES.new(self.key, AES.MODE_CBC, self.key[:16])
            plain = unpad(
                cipher.decrypt(base64.b64decode(encrypt)), _BLOCK_BYTES
            )
        except Exception as exc:
            raise WecomCryptoError(f"decrypt_failed: {exc}") from exc
        if len(plain) < 20:
            raise WecomCryptoError("plaintext_too_short")
        msg_len = struct.unpack(">I", plain[16:20])[0]
        msg = plain[20 : 20 + msg_len]
        if len(msg) != msg_len:
            raise WecomCryptoError("msg_length_mismatch")
        return msg.decode("utf-8")

    def encrypt(self, message: str) -> str:
        msg = message.encode("utf-8")
        payload = (
            os.urandom(16)
            + struct.pack(">I", len(msg))
            + msg
            + self.receive_id.encode("utf-8")
        )
        cipher = AES.new(self.key, AES.MODE_CBC, self.key[:16])
        return base64.b64encode(
            cipher.encrypt(pad(payload, _BLOCK_BYTES))
        ).decode("utf-8")
