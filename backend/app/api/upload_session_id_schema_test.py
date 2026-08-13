from app.db.database import _uploaded_files_session_id_alter_sql
from app.knowledge_base.models import UploadedFile
from app.api.upload_routes import _content_disposition


def test_uploaded_file_session_id_accepts_react_mode_session_ids():
    assert UploadedFile.__table__.c.session_id.type.length == 255


def test_uploaded_file_session_id_migration_widens_postgresql_column():
    assert _uploaded_files_session_id_alter_sql("postgresql") == (
        "ALTER TABLE uploaded_files ALTER COLUMN session_id TYPE VARCHAR(255)"
    )


def test_upload_content_disposition_supports_unicode_filenames():
    header = _content_disposition("inline", "濮阳市智慧环保建设项目二期 系统架构图.png")

    header.encode("latin-1")
    assert header.startswith('inline; filename="')
    assert "filename*=UTF-8''" in header
    assert "%E6%BF%AE%E9%98%B3" in header
