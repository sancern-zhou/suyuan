from app.agent.memory.session_memory import SessionMemory


def test_default_session_memory_uses_active_project_data_registry(monkeypatch, tmp_path):
    import app.agent.memory.session_memory as session_memory_module

    sessions_dir = tmp_path / "backend_data_registry_jiangsu_ops" / "sessions"
    monkeypatch.setattr(session_memory_module, "get_sessions_dir", lambda: sessions_dir)

    memory = SessionMemory("jiangsu-session", use_llm_compression=False)

    assert memory.session_dir == sessions_dir / "agent_session_jiangsu-session"
