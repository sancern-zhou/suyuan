from app.tools.utility.read_file_tool import ReadFileTool


def test_read_file_schema_does_not_claim_resource_registration_or_preview_creation():
    tool = ReadFileTool()
    schema = tool.get_function_schema()

    assert "knowledge_document_reader" in schema["description"]
    assert "不注册资源" in tool.description
    assert "enable_preview" not in schema["parameters"]["properties"]
