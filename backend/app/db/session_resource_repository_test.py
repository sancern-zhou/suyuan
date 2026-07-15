from app.db.models_session import SessionResourceManifestDB


def test_manifest_table_is_independent_from_transcript_tables():
    table = SessionResourceManifestDB.__table__
    assert table.name == "session_resource_manifests"
    assert table.c.session_id.primary_key is True
    assert list(table.foreign_keys) == []
    assert {"session_id", "resource_refs", "version", "created_at", "updated_at"} <= set(table.c.keys())
