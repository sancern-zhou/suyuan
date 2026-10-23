from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import file_manager_routes
from app.auth.dependencies import require_current_user
from app.auth.models import CurrentUser


def test_shared_temporary_files_require_administrator(tmp_path, monkeypatch):
    private = tmp_path / "alice-report.txt"
    private.write_text("synthetic", encoding="utf-8")
    monkeypatch.setattr(file_manager_routes, "ALLOWED_ROOT", tmp_path)
    app = FastAPI()
    app.include_router(file_manager_routes.router)
    user = CurrentUser(id="bob", username="bob", display_name="Bob")
    app.dependency_overrides[require_current_user] = lambda: user
    with TestClient(app) as client:
        for path in ["list", "download", "info"]:
            response = client.get(f"/file-manager/{path}", params={"path": private.name})
            assert response.status_code == 403
        user = user.model_copy(update={"is_admin": True})
        assert client.get("/file-manager/download", params={"path": private.name}).text == "synthetic"
        assert client.get("/file-manager/test").status_code == 404
