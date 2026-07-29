from app.tools.office.editable_ppt.tool import ManageEditablePptTool


def test_compile_schema_defaults_to_strict_for_long_decks():
    branches = ManageEditablePptTool().get_function_schema()["parameters"]["oneOf"]
    compile_branch = next(item for item in branches if item["properties"]["operation"]["const"] == "compile")
    assert compile_branch["properties"]["editable"]["default"] == "strict"
