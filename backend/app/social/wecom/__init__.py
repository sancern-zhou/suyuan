"""WeCom (企业微信) 客户联系推送渠道.

Public surface:
- ``WecomCrypto``: callback signature check + AES-256-CBC encrypt/decrypt.
- ``WecomClient``: token / group-msg template / contact-way QR HTTP client.
- ``WecomBindingStore``: app-account ↔ external_userid binding registry.
- ``get_wecom_client``: process-level singleton client.
"""
