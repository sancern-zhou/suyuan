"""
重构验证测试

验证 loop.py 重构后的基本功能是否正常。
"""

import pytest
from app.agent.core.formatters import (
    FormatterRegistry,
    BashFormatter,
    ImageFormatter,
    FileFormatter,
    GrepFormatter,
    OfficeFormatter,
    DataQueryFormatter,
    StatisticsFormatter,
    DetailedResultFormatter,
)


class TestFormatterModule:
    """测试格式化器模块"""

    def test_formatter_registry_creation(self):
        """测试格式化器注册表创建"""
        registry = FormatterRegistry()
        assert registry is not None
        assert registry.get_formatter_count() == 0

    def test_formatter_registration(self):
        """测试格式化器注册"""
        registry = FormatterRegistry()
        registry.register(BashFormatter)
        registry.register(ImageFormatter)
        assert registry.get_formatter_count() == 2

    def test_bash_formatter(self):
        """测试 Bash 格式化器"""
        data = {
            "stdout": "Hello World",
            "stderr": "",
            "exit_code": 0,
            "command": "echo hello"
        }
        metadata = {"generator": "bash"}

        formatter = BashFormatter()
        result = formatter.format(data, metadata)

        assert len(result) > 0
        assert any("Hello World" in line for line in result)
        assert any("命令输出" in line for line in result)

    def test_image_formatter(self):
        """测试 Image 格式化器"""
        data = {"analysis": "This is a test image analysis"}
        metadata = {"generator": "analyze_image"}

        formatter = ImageFormatter()
        result = formatter.format(data, metadata)

        assert len(result) > 0
        assert any("This is a test image analysis" in line for line in result)

    def test_file_formatter(self):
        """测试 File 格式化器"""
        data = {
            "type": "text",
            "content": "File content here"
        }
        metadata = {"generator": "read_file"}

        formatter = FileFormatter()
        result = formatter.format(data, metadata)

        assert len(result) > 0
        assert any("File content here" in line for line in result)

    def test_formatter_can_handle(self):
        """测试格式化器 can_handle 方法"""
        assert BashFormatter.can_handle("bash", {"stdout": "test"}) is True
        assert BashFormatter.can_handle("bash", {"data": "test"}) is False
        assert ImageFormatter.can_handle("analyze_image", {"analysis": "test"}) is True
        assert ImageFormatter.can_handle("analyze_image", {"data": "test"}) is False

    def test_formatter_priority(self):
        """测试格式化器优先级"""
        assert BashFormatter.get_priority() == 5
        assert ImageFormatter.get_priority() == 10
        assert FileFormatter.get_priority() == 11


class TestDataFormatters:
    """测试数据格式化器"""

    def test_data_query_formatter(self):
        """测试数据查询格式化器"""
        observation = {
            "success": True,
            "data": [
                {"id": 1, "name": "Item 1"},
                {"id": 2, "name": "Item 2"}
            ],
            "metadata": {
                "sampling_applied": True,
                "original_record_count": 100,
                "sampling_info": {
                    "strategy": "head_tail_middle_sampling",
                    "head_samples": 1,
                    "middle_samples": 0,
                    "tail_samples": 1
                }
            }
        }

        formatter = DataQueryFormatter()
        result = formatter.format(observation)

        assert len(result) > 0
        assert any("数据预览" in line for line in result)
        assert any("采样2条" in line or "2条" in line for line in result)

    def test_statistics_formatter(self):
        """测试统计格式化器"""
        data_dict = {
            "total": 100,
            "average": 50.5,
            "max": 99
        }

        formatter = StatisticsFormatter()
        result = formatter.format(data_dict)

        assert len(result) > 0
        assert any("统计结果" in line for line in result)


class TestIntegration:
    """集成测试"""

    def test_formatter_registry_with_multiple_formatters(self):
        """测试多个格式化器的注册和查找"""
        registry = FormatterRegistry()

        # 注册多个格式化器
        formatters = [
            BashFormatter,
            ImageFormatter,
            FileFormatter,
            GrepFormatter,
            OfficeFormatter,
        ]

        for formatter in formatters:
            registry.register(formatter)

        assert registry.get_formatter_count() == len(formatters)

        # 测试查找正确的格式化器
        bash_data = {"stdout": "test"}
        formatter = registry.get_formatter("bash", bash_data)
        assert formatter == BashFormatter

        image_data = {"analysis": "test"}
        formatter = registry.get_formatter("analyze_image", image_data)
        assert formatter == ImageFormatter

    def test_formatter_priority_ordering(self):
        """测试格式化器按优先级排序"""
        registry = FormatterRegistry()

        # 按非优先级顺序注册
        registry.register(FileFormatter)  # priority 11
        registry.register(BashFormatter)  # priority 5
        registry.register(ImageFormatter) # priority 10

        # 验证格式化器按优先级排序（优先级数字越小越靠前）
        formatters = registry.list_formatters()
        # BashFormatter (priority 5) 应该排在最前面
        assert "BashFormatter" in formatters
        # 验证最低优先级数字的格式化器存在
        bash_index = formatters.index("BashFormatter")
        image_index = formatters.index("ImageFormatter")
        file_index = formatters.index("FileFormatter")

        # Bash (5) < Image (10) < File (11)
        assert bash_index < image_index < file_index


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
