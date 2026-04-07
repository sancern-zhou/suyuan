"""
修改province_statistics表的sample_coverage字段

将sample_coverage从DECIMAL(5,2)修改为DECIMAL(10,2)
以支持省级统计中可能出现的较大值
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from app.fetchers.city_statistics.city_statistics_fetcher import SQLServerClient
import structlog

logger = structlog.get_logger()


def alter_province_table():
    """修改province_statistics表的sample_coverage字段"""
    client = SQLServerClient()

    # 测试连接
    if not client.test_connection():
        logger.error("sql_server_connection_failed")
        print("数据库连接失败，请检查连接配置")
        return False

    logger.info("sql_server_connection_success")
    print("数据库连接成功\n")

    # 修改表的SQL脚本
    sql_script = """
-- 修改sample_coverage字段
ALTER TABLE province_statistics
ALTER COLUMN sample_coverage DECIMAL(10,2);

PRINT 'sample_coverage字段已从DECIMAL(5,2)修改为DECIMAL(10,2)';
"""

    try:
        import pyodbc
        conn = pyodbc.connect(client.connection_string, timeout=30)
        cursor = conn.cursor()

        cursor.execute(sql_script)
        conn.commit()

        cursor.close()
        conn.close()

        print("\n" + "="*60)
        print("province_statistics表字段修改成功！")
        print("sample_coverage: DECIMAL(5,2) -> DECIMAL(10,2)")
        print("="*60)
        return True

    except Exception as e:
        logger.error(
            "alter_province_table_failed",
            error=str(e),
            exc_info=True
        )
        print(f"修改表失败: {str(e)}")
        return False


if __name__ == "__main__":
    alter_province_table()
