from app.knowledge_base.document_processor import DocumentProcessor


def test_preprocess_toc_never_deletes_split_line_body_sections():
    content = """中华人民共和国国家生态环境标准
目
次
前
言........................................................ii
1
适用范围....................................................1
2
规范性引用文件..............................................1

ii
前
言
这是必须保留的前言正文。

1
适用范围
这是必须保留的第一章正文。

6
性能指标
性能指标应分别符合表2中的要求。
检测项目
7.14
24 h 漂移
20%量程

7
检测方法
这是第七章正文。
"""

    processed = DocumentProcessor()._preprocess_content(content)

    assert "这是必须保留的前言正文" in processed
    assert "这是必须保留的第一章正文" in processed
    assert "性能指标应分别符合表2中的要求" in processed
    assert "24 h 漂移" in processed
    assert "这是第七章正文" in processed
    assert "适用范围....................................................1" not in processed


def test_preprocess_keeps_uncertain_toc_text_instead_of_deleting_body_range():
    content = """目录
第一部分 说明 1
第二部分 要求 3

前言
正文开头不能被删除。

1 总则
总则的完整正文。
"""

    processed = DocumentProcessor()._preprocess_content(content)

    # 没有点引导符的非标准目录宁可残留，也不能导致正文被范围删除。
    assert "第一部分 说明 1" in processed
    assert "第二部分 要求 3" in processed
    assert "正文开头不能被删除" in processed
    assert "总则的完整正文" in processed


def test_numeric_and_formula_heavy_segment_is_not_toc():
    content = """10.1 结果计算
C
1
=
m
1
/ V
表1 测定结果
1
0.021
0.002
2
0.203
0.016
3
1.01
0.068
正文中的公式、数字和表格必须保留。
"""

    assert DocumentProcessor()._is_toc_content(content) is False


def test_dotted_contents_segment_is_toc():
    content = """目 次
前言................................ii
1 适用范围..........................1
2 规范性引用文件....................2
3 术语和定义........................3
4 方法原理..........................4
"""

    assert DocumentProcessor()._is_toc_content(content) is True
