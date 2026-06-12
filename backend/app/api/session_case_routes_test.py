from pathlib import Path


SESSION_ROUTES = (Path(__file__).resolve().parent / "session_routes.py").read_text(encoding="utf-8")
SESSION_MANAGER_DB = (
    Path(__file__).resolve().parents[1] / "agent/session/session_manager_db.py"
).read_text(encoding="utf-8")
SESSION_REPOSITORY = (
    Path(__file__).resolve().parents[1] / "db/session_repository.py"
).read_text(encoding="utf-8")


def test_session_routes_expose_case_mark_endpoints():
    assert '@router.post("/{session_id}/case")' in SESSION_ROUTES
    assert '@router.delete("/{session_id}/case")' in SESSION_ROUTES


def test_case_marking_uses_session_metadata():
    assert '"is_case"' in SESSION_ROUTES
    assert '"case_marked_at"' in SESSION_ROUTES
    assert "save_session_metadata" in SESSION_ROUTES


def test_session_list_preserves_metadata_for_case_filtering():
    assert '"metadata": self._session_summary_metadata(s.session_metadata)' in SESSION_REPOSITORY
    assert 'metadata=summary["metadata"]' in SESSION_MANAGER_DB


def test_session_list_uses_bounded_default_limit():
    assert "SESSION_LIST_DEFAULT_LIMIT = 50" in SESSION_ROUTES
    assert "SESSION_LIST_MAX_LIMIT = 200" in SESSION_ROUTES
    assert "effective_limit = min(limit or SESSION_LIST_DEFAULT_LIMIT, SESSION_LIST_MAX_LIMIT)" in SESSION_ROUTES


def test_session_repository_list_uses_lightweight_columns():
    list_method = SESSION_REPOSITORY.split("async def list_sessions", 1)[1].split(
        "async def save_conversation_history", 1
    )[0]
    assert "select(SessionDB)" not in list_method
    assert "SessionDB.office_documents" not in list_method
    assert "result.all()" in list_method
    assert "result.scalars().all()" not in list_method


def test_session_stats_use_database_aggregate():
    assert "async def get_session_stats_summary" in SESSION_REPOSITORY
    assert "get_session_stats_summary" in SESSION_MANAGER_DB
    stats_method = SESSION_MANAGER_DB.split("async def get_session_stats", 1)[1].split(
        "async def export_session", 1
    )[0]
    assert "list_sessions(limit=10000)" not in stats_method


def test_lazy_restore_preserves_lightweight_session_metadata():
    restore_method = SESSION_ROUTES.split('@router.post("/{session_id}/restore")', 1)[1].split(
        '@router.post("/auto-save")', 1
    )[0]
    assert "has_lazy_drawio_board" in restore_method
    assert "get_session_metadata" in restore_method
    assert '@router.get("/{session_id}/drawio-board")' in SESSION_ROUTES
