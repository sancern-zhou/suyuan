from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CONFIG = ROOT / "deploy/nginx/templates/default.conf.template"


def test_nginx_routes_auth_business_websocket_and_spa():
    text = CONFIG.read_text(encoding="utf-8")

    assert "listen ${LISTEN_PORT}" in text
    assert "location ^~ /api/auth/" in text
    assert "proxy_pass ${AUTH_UPSTREAM};" in text
    assert "location ^~ /api/suyuan/ws/" in text
    assert "proxy_pass ${BUSINESS_UPSTREAM}/ws/;" in text
    assert "location ^~ /api/suyuan/" in text
    assert "proxy_pass ${BUSINESS_UPSTREAM}/api/;" in text
    assert 'proxy_set_header X-User-Id "";' in text
    assert 'proxy_set_header X-Is-Admin "";' in text
    assert "try_files $uri $uri/ /index.html;" in text
