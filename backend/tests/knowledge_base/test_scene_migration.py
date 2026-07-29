from app.alembic.versions import add_scenario_driven_knowledge_graph as migration


def test_migration_declares_all_scene_tables_and_columns():
    sql = "\n".join(migration.KNOWLEDGE_BASE_ALTERS)
    assert "scene_status" in sql
    assert "scene_profile_version" in sql
    assert "schema_version" in sql
    assert "rule_version" in sql
    graph_sql = "\n".join(migration.GRAPH_FACT_ALTERS)
    assert "source_type" in graph_sql
    assert "scene_profile_version" in graph_sql
    assert {table.name for table in migration.SCENE_TABLES} == {
        "knowledge_scene_profiles",
        "knowledge_business_rules",
        "knowledge_user_facts",
        "knowledge_schema_suggestions",
        "knowledge_graph_extraction_runs",
    }
