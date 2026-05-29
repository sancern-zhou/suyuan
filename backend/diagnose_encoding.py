#!/usr/bin/env python3
"""深度诊断编码问题的根本原因"""

import pyodbc
from config.settings import Settings

def diagnose_encoding_issue():
    """诊断编码问题的根本原因"""

    settings = Settings()
    connection_string = (
        f"DRIVER={{{settings.sqlserver_driver}}};"
        f"SERVER={settings.sqlserver_host},{settings.sqlserver_port};"
        f"DATABASE=AirPollutionAnalysis;"
        f"UID={settings.sqlserver_user};"
        f"PWD={{{settings.sqlserver_password}}};"
        f"TrustServerCertificate=yes;"
    )

    conn = pyodbc.connect(connection_string, timeout=30)
    cursor = conn.cursor()

    print("=" * 80)
    print("深度诊断：编码问题根本原因")
    print("=" * 80)

    # 获取问题记录
    sql = """
    SELECT TOP 5
        WORKINGORDERCODE,
        ORDERTITLE,
        ORDERCONTENT,
        DDWORKINGORDERTYPE
    FROM dbo.working_orders
    WHERE ORDERTITLE LIKE N'%?%'
    AND ORDERTITLE NOT LIKE N'%任务%'
    AND ORDERTITLE NOT LIKE N'%计划%'
    ORDER BY FINISHTIME DESC
    """

    cursor.execute(sql)
    results = cursor.fetchall()

    for i, row in enumerate(results, 1):
        title = row[1]
        content = row[2]
        order_type = row[3]

        print(f"\n记录 {i}: {row[0]} (类型: {order_type})")
        print("-" * 60)

        # 尝试不同的编码解码
        print(f"原始标题: {title}")
        print(f"原始字节: {title.encode('utf-8')}")
        print(f"字节长度: {len(title.encode('utf-8'))}")

        # 尝试从GBK解码
        try:
            # 假设原始数据是GBK，被错误地按UTF-8读取
            # 尝试反向操作：UTF-8编码 -> GBK解码
            gbk_decoded = title.encode('latin-1').decode('gbk', errors='ignore')
            print(f"尝试Latin-1编码->GBK解码: {gbk_decoded}")
        except Exception as e:
            print(f"Latin-1->GBK失败: {e}")

        # 尝试从GB2312解码
        try:
            gb2312_decoded = title.encode('latin-1').decode('gb2312', errors='ignore')
            print(f"尝试Latin-1编码->GB2312解码: {gb2312_decoded}")
        except Exception as e:
            print(f"Latin-1->GB2312失败: {e}")

        # 检查是否是UTF-8被错误地按Latin-1读取
        try:
            # 假设原始是UTF-8，被错误地按Latin-1读取
            # Latin-1解码 -> UTF-8解码
            latin1_bytes = title.encode('utf-8')
            utf8_decoded = latin1_bytes.decode('utf-8', errors='ignore')
            print(f"尝试反向UTF-8: {utf8_decoded}")
        except Exception as e:
            print(f"反向UTF-8失败: {e}")

    print("\n" + "=" * 80)
    print("检查数据库列的字符集设置")
    print("=" * 80)

    # 查询列的字符集信息
    sql2 = """
    SELECT
        c.COLUMN_NAME,
        c.DATA_TYPE,
        c.CHARACTER_MAXIMUM_LENGTH,
        c.CHARACTER_SET_NAME,
        c.COLLATION_NAME
    FROM INFORMATION_SCHEMA.COLUMNS c
    WHERE c.TABLE_NAME = 'working_orders'
    AND c.COLUMN_NAME IN ('ORDERTITLE', 'ORDERCONTENT', 'StationName')
    """

    try:
        cursor.execute(sql2)
        columns_info = cursor.fetchall()

        print(f"\n{'列名':<20} {'数据类型':<20} {'最大长度':<10} {'字符集':<20} {'排序规则':<30}")
        print("-" * 100)
        for row in columns_info:
            print(f"{row[0]:<20} {row[1]:<20} {str(row[2]):<10} {str(row[3]):<20} {str(row[4]):<30}")
    except Exception as e:
        print(f"查询字符集信息失败: {e}")

    print("\n" + "=" * 80)
    print("测试：直接读取原始字节")
    print("=" * 80)

    # 获取一条问题记录的原始数据
    sql3 = """
    SELECT TOP 1
        WORKINGORDERCODE,
        ORDERTITLE,
        ORDERCONTENT
    FROM dbo.working_orders
    WHERE ORDERTITLE LIKE N'%?%'
    AND ORDERTITLE NOT LIKE N'%任务%'
    """

    cursor.execute(sql3)
    result = cursor.fetchone()

    if result:
        title = result[1]

        print(f"原始数据: {title}")
        print(f"repr(): {repr(title)}")
        print(f"UTF-8编码: {title.encode('utf-8')}")
        print(f"UTF-8编码(hex): {title.encode('utf-8').hex()}")

        # 检查每个字符
        print("\n字符分析:")
        for i, char in enumerate(title[:10]):  # 只分析前10个字符
            code_point = ord(char)
            print(f"  字符{i}: '{char}' (U+{code_point:04X})")
            if code_point < 128:
                print(f"    -> ASCII字符")
            elif code_point == 65533:
                print(f"    -> Unicode替换字符")
            elif 0xD800 <= code_point <= 0xDFFF:
                print(f"    -> 代理对字符")

    print("\n" + "=" * 80)
    print("结论和建议")
    print("=" * 80)

    print("""
可能的编码问题原因：

1. **数据库写入时的编码错误**：
   - 应用程序在写入数据库时使用了错误的字符集
   - 例如：将GBK编码的字符串按UTF-8写入，或反之

2. **数据库读取时的编码错误**：
   - pyodbc连接字符串没有指定正确的字符集
   - 需要添加 charset=gbk 或 charset=utf8 参数

3. **数据库列的字符集设置不当**：
   - SQL Server列的排序规则可能不是中文友好的
   - 应该使用 Chinese_PRC_CI_AS

建议的解决方案：

1. **立即方案**：在连接字符串中添加字符集参数
   - 尝试 charset=gbk 或 charset=utf8

2. **数据修复**：编写脚本修复已有数据
   - 尝试反向解码修复历史数据

3. **预防措施**：
   - 确保所有写入操作使用UTF-8编码
   - 在数据库列上设置正确的排序规则
    """)

    cursor.close()
    conn.close()

if __name__ == "__main__":
    diagnose_encoding_issue()
