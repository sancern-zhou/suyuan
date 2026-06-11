"""Configuration encryption/decryption utilities for local social credentials."""

from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path

try:
    from cryptography.fernet import Fernet
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False


class ConfigCrypto:
    """Small local encryption helper for social account tokens."""

    _FALLBACK_PREFIX = "enc:v1:"

    def __init__(self, secret_key_path: str | None = None):
        if secret_key_path is None:
            from config.settings import settings
            secret_key_path = Path(settings.data_registry_dir) / "social" / ".crypto_key"
        else:
            secret_key_path = Path(secret_key_path)

        self._key_path = secret_key_path
        self._key_path.parent.mkdir(parents=True, exist_ok=True)
        self._key = self._load_or_generate_key()
        self._fernet = Fernet(self._key) if CRYPTO_AVAILABLE else None
        try:
            self._aes_key = base64.urlsafe_b64decode(self._key)
        except Exception:
            self._aes_key = hashlib.sha256(self._key).digest()
        if len(self._aes_key) != 32:
            self._aes_key = hashlib.sha256(self._aes_key).digest()

    def _load_or_generate_key(self) -> bytes:
        if self._key_path.exists():
            try:
                return self._key_path.read_bytes()
            except Exception:
                pass

        key = Fernet.generate_key() if CRYPTO_AVAILABLE else base64.urlsafe_b64encode(os.urandom(32))
        try:
            self._key_path.write_bytes(key)
            os.chmod(self._key_path, 0o600)
        except Exception:
            pass
        return key

    def _fallback_encrypt(self, value: str) -> str:
        from Crypto.Cipher import AES

        nonce = os.urandom(12)
        cipher = AES.new(self._aes_key, AES.MODE_GCM, nonce=nonce)
        ciphertext, tag = cipher.encrypt_and_digest(value.encode())
        payload = base64.urlsafe_b64encode(nonce + tag + ciphertext).decode()
        return f"{self._FALLBACK_PREFIX}{payload}"

    def _fallback_decrypt(self, encrypted_value: str) -> str:
        from Crypto.Cipher import AES

        payload = encrypted_value[len(self._FALLBACK_PREFIX):]
        raw = base64.urlsafe_b64decode(payload.encode())
        nonce, tag, ciphertext = raw[:12], raw[12:28], raw[28:]
        cipher = AES.new(self._aes_key, AES.MODE_GCM, nonce=nonce)
        return cipher.decrypt_and_verify(ciphertext, tag).decode()

    def encrypt(self, value: str) -> str:
        if not value:
            return ""
        if self._fernet:
            return base64.urlsafe_b64encode(self._fernet.encrypt(value.encode())).decode()
        return self._fallback_encrypt(value)

    def decrypt(self, encrypted_value: str) -> str:
        if not encrypted_value:
            return ""
        try:
            if encrypted_value.startswith(self._FALLBACK_PREFIX):
                return self._fallback_decrypt(encrypted_value)
            if not self._fernet:
                return encrypted_value
            return self._fernet.decrypt(base64.urlsafe_b64decode(encrypted_value.encode())).decode()
        except Exception:
            return encrypted_value


_crypto_instance: ConfigCrypto | None = None


def get_config_crypto() -> ConfigCrypto:
    global _crypto_instance
    if _crypto_instance is None:
        _crypto_instance = ConfigCrypto()
    return _crypto_instance
