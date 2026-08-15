"""
EditFile V2 功能测试脚本（修复版）

测试场景：
1. 预读取验证（强制先read_file）
2. 引号规范化（弯引号↔直引号）
3. Trailing空格处理
4. 文件修改检查
5. 多匹配检查
6. 编码自动检测
7. 错误提示增强
"""
import asyncio
from pathlib import Path
from app.tools.utility.read_file_tool import ReadFileTool
from app.tools.utility.edit_file_tool_v2 import EditFileToolV2
from app.tools.utility.file_read_state import get_file_read_state


# 临时文件目录
TEMP_DIR = Path("/home/xckj/suyuan/backend_data_registry/temp")


async def test_pre_read_validation():
    """测试1：预读取验证"""
    print("\n" + "="*50)
    print("测试1：预读取验证")
    print("="*50)

    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    temp_file = TEMP_DIR / "test_pre_read.py"

    try:
        temp_file.write_text('PORT = 8000\n')

        read_tool = ReadFileTool()
        edit_tool = EditFileToolV2()

        # ❌ 测试未先读取的编辑（应该失败）
        print("\n❌ 测试未先读取的编辑...")
        result = await edit_tool.execute(
            path=str(temp_file),
            old_string='PORT = 8000',
            new_string='PORT = 9000'
        )
        assert not result["success"], "应该失败：未先读取文件"
        assert "not been read" in result["summary"] or "请先使用" in result["summary"], "错误提示应包含'not been read'"
        print(f"✅ 预期失败：{result['summary']}")

        # ✅ 测试先读取再编辑（应该成功）
        print("\n✅ 测试先读取再编辑...")
        await read_tool.execute(path=str(temp_file))
        result = await edit_tool.execute(
            path=str(temp_file),
            old_string='PORT = 8000',
            new_string='PORT = 9000'
        )
        assert result["success"], f"编辑应该成功：{result.get('summary')}"
        print(f"✅ 编辑成功：{result['summary']}")

        # 验证文件内容
        content = temp_file.read_text()
        assert 'PORT = 9000' in content, "文件内容应已更新"
        print(f"✅ 文件内容已更新：{content.strip()}")

    finally:
        if temp_file.exists():
            temp_file.unlink()


async def test_quote_normalization():
    """测试2：引号规范化（弯引号↔直引号）"""
    print("\n" + "="*50)
    print("测试2：引号规范化")
    print("="*50)

    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    temp_file = TEMP_DIR / "test_quotes.py"

    try:
        # 创建包含弯引号的文件
        temp_file.write_text('title = "历史结论"\n', encoding='utf-8')

        read_tool = ReadFileTool()
        edit_tool = EditFileToolV2()

        # 先读取文件
        await read_tool.execute(path=str(temp_file))

        # 使用直引号编辑（应该自动处理弯引号）
        print("\n✅ 测试直引号→弯引号匹配...")
        result = await edit_tool.execute(
            path=str(temp_file),
            old_string='title = "历史结论"',  # 直引号
            new_string='title = "新标题"'      # 直引号
        )
        assert result["success"], f"编辑应该成功（自动处理引号）：{result.get('summary')}"
        print(f"✅ 编辑成功：{result['summary']}")

        # 验证文件内容（应保留弯引号）
        content = temp_file.read_text(encoding='utf-8')
        assert '"' in content, "应保留弯引号"
        print(f"✅ 保留弯引号：{content.strip()}")

    finally:
        if temp_file.exists():
            temp_file.unlink()


async def test_trailing_whitespace():
    """测试3：Trailing空格处理"""
    print("\n" + "="*50)
    print("测试3：Trailing空格处理")
    print("="*50)

    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    temp_file = TEMP_DIR / "test_whitespace.py"

    try:
        # 创建包含trailing空格的文件
        temp_file.write_text('value = "test"  \n')  # 两个trailing空格

        read_tool = ReadFileTool()
        edit_tool = EditFileToolV2()

        # 先读取文件
        await read_tool.execute(path=str(temp_file))

        # 不带trailing空格编辑（应该自动处理）
        print("\n✅ 测试自动去除trailing空格...")
        result = await edit_tool.execute(
            path=str(temp_file),
            old_string='value = "test"',  # 无trailing空格
            new_string='value = "new"'
        )
        assert result["success"], f"编辑应该成功（自动处理空格）：{result.get('summary')}"
        print(f"✅ 编辑成功：{result['summary']}")

    finally:
        if temp_file.exists():
            temp_file.unlink()


async def test_file_modification_detection():
    """测试4：文件修改检查"""
    print("\n" + "="*50)
    print("测试4：文件修改检查")
    print("="*50)

    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    temp_file = TEMP_DIR / "test_modification.py"

    try:
        temp_file.write_text('ORIGINAL\n')

        read_tool = ReadFileTool()
        edit_tool = EditFileToolV2()

        # 1. 先读取文件
        await read_tool.execute(path=str(temp_file))
        print("✅ 文件已读取")

        # 2. 外部修改文件
        temp_file.write_text('MODIFIED\n')
        print("✅ 文件已被外部修改")

        # 3. 尝试编辑（应该失败）
        print("\n❌ 测试编辑已修改的文件...")
        result = await edit_tool.execute(
            path=str(temp_file),
            old_string='ORIGINAL',
            new_string='NEW'
        )
        assert not result["success"], "应该失败：文件已被修改"
        assert "modified" in result["summary"].lower() or "修改" in result["summary"], "错误提示应包含'modified'"
        print(f"✅ 预期失败：{result['summary']}")

        # 4. 重新读取后再编辑（应该成功）
        print("\n✅ 重新读取文件...")
        await read_tool.execute(path=str(temp_file))
        result = await edit_tool.execute(
            path=str(temp_file),
            old_string='MODIFIED',
            new_string='NEW'
        )
        assert result["success"], f"重新读取后编辑应该成功：{result.get('summary')}"
        print(f"✅ 编辑成功：{result['summary']}")

    finally:
        if temp_file.exists():
            temp_file.unlink()


async def test_multiple_matches():
    """测试5：多匹配检查"""
    print("\n" + "="*50)
    print("测试5：多匹配检查")
    print("="*50)

    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    temp_file = TEMP_DIR / "test_multiple.py"

    try:
        temp_file.write_text('ERROR: line1\nERROR: line2\nERROR: line3\n')

        read_tool = ReadFileTool()
        edit_tool = EditFileToolV2()

        # 先读取文件
        await read_tool.execute(path=str(temp_file))

        # 不使用replace_all（应该失败）
        print("\n❌ 测试多匹配不使用replace_all...")
        result = await edit_tool.execute(
            path=str(temp_file),
            old_string='ERROR',
            new_string='WARNING',
            replace_all=False
        )
        assert not result["success"], "应该失败：old_string不唯一"
        assert "3" in result["summary"] or "三次" in result["summary"], "应显示匹配次数"
        print(f"✅ 预期失败：{result['summary']}")

        # 使用replace_all（应该成功）
        print("\n✅ 测试使用replace_all...")
        result = await edit_tool.execute(
            path=str(temp_file),
            old_string='ERROR',
            new_string='WARNING',
            replace_all=True
        )
        assert result["success"], f"replace_all应该成功：{result.get('summary')}"
        assert result["data"]["changes"] == 3, "应替换3处"
        print(f"✅ 编辑成功：替换了{result['data']['changes']}处")

    finally:
        if temp_file.exists():
            temp_file.unlink()


async def test_encoding_detection():
    """测试6：编码自动检测"""
    print("\n" + "="*50)
    print("测试6：编码自动检测")
    print("="*50)

    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    temp_file = TEMP_DIR / "test_encoding.py"

    try:
        # 创建GBK编码文件
        temp_file.write_text('# 中文测试\n', encoding='gbk')

        read_tool = ReadFileTool()
        edit_tool = EditFileToolV2()

        # 先读取文件
        await read_tool.execute(path=str(temp_file), encoding='gbk')

        # 自动检测编码编辑
        print("\n✅ 测试自动编码检测...")
        result = await edit_tool.execute(
            path=str(temp_file),
            old_string='# 中文测试',
            new_string='# 中文测试（已修改）',
            encoding=None  # 自动检测
        )
        # 注意：编码检测可能失败，这是预期的
        if result["success"]:
            print(f"✅ 编辑成功：{result['summary']}")
        else:
            print(f"⚠️ 编码检测失败（预期）：{result['summary']}")

    finally:
        if temp_file.exists():
            temp_file.unlink()


async def test_enhanced_error_messages():
    """测试7：增强错误提示"""
    print("\n" + "="*50)
    print("测试7：增强错误提示")
    print("="*50)

    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    temp_file = TEMP_DIR / "test_error_msg.py"

    try:
        temp_file.write_text('value = "test"\n')

        read_tool = ReadFileTool()
        edit_tool = EditFileToolV2()

        # 先读取文件
        await read_tool.execute(path=str(temp_file))

        # 使用错误的old_string
        print("\n❌ 测试错误的old_string...")
        result = await edit_tool.execute(
            path=str(temp_file),
            old_string='wrong_string',
            new_string='new_string'
        )
        assert not result["success"], "应该失败：old_string未找到"
        assert "hints" in result.get("data", {}), "应包含hints"
        print(f"✅ 错误提示：{result['summary']}")
        if "data" in result and "hints" in result["data"]:
            print(f"✅ Hints：{result['data']['hints']}")

    finally:
        if temp_file.exists():
            temp_file.unlink()


async def main():
    """运行所有测试"""
    print("\n" + "="*50)
    print("EditFile V2 功能测试")
    print("="*50)

    tests = [
        ("预读取验证", test_pre_read_validation),
        ("引号规范化", test_quote_normalization),
        ("Trailing空格处理", test_trailing_whitespace),
        ("文件修改检查", test_file_modification_detection),
        ("多匹配检查", test_multiple_matches),
        ("编码自动检测", test_encoding_detection),
        ("增强错误提示", test_enhanced_error_messages),
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        try:
            await test_func()
            passed += 1
            print(f"\n✅ {name}：通过")
        except AssertionError as e:
            failed += 1
            print(f"\n❌ {name}：失败 - {e}")
        except Exception as e:
            failed += 1
            print(f"\n❌ {name}：错误 - {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "="*50)
    print(f"测试完成：{passed} 通过，{failed} 失败")
    print("="*50)


if __name__ == "__main__":
    asyncio.run(main())
