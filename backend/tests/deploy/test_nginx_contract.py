import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CONFIG = ROOT / "deploy/nginx/templates/default.conf.template"
COMPOSE = ROOT / "deploy/nginx/docker-compose.yml"
STANDALONE_ENV = ROOT / "frontend/.env.standalone"
PACKAGE_JSON = ROOT / "frontend/package.json"


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


def test_compose_uses_host_network_read_only_mounts_and_restart_policy():
    text = COMPOSE.read_text(encoding="utf-8")

    assert "network_mode: host" in text
    assert "restart: unless-stopped" in text
    assert "../../frontend/dist:/usr/share/nginx/html:ro" in text
    assert "./templates:/etc/nginx/templates:ro" in text
    assert "${SUYUAN_NGINX_PORT:-5174}" in text
    assert "${AUTH_UPSTREAM:-http://10.10.204.80:8025}" in text
    assert "${BUSINESS_UPSTREAM:-http://127.0.0.1:8000}" in text


def test_standalone_build_keeps_the_existing_root_login_url():
    env_text = STANDALONE_ENV.read_text(encoding="utf-8")
    package = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))

    assert "VITE_APP_BASE_PATH=/" in env_text
    assert "VITE_API_BASE_URL=/api/suyuan" in env_text
    assert package["scripts"]["build:standalone"] == "vite build --mode standalone"


def test_default_build_targets_the_public_root_nginx_deployment():
    package = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))

    assert package["scripts"]["build"] == "vite build --mode standalone"
    assert package["scripts"]["build:gateway"] == "vite build --mode production"
