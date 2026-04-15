"""
质控例行检查表创建脚本

在现有的 SQL Server 数据库中创建质控表
"""

import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pyodbc
from config.settings import Settings
import structlog

logger = structlog.get_logger()


def create_quality_control_table():
    """创建质控例行检查记录表"""

    settings = Settings()
    connection_string = settings.sqlserver_connection_string

    logger.info("开始创建质控表")

    try:
        conn = pyodbc.connect(connection_string, timeout=30)
        cursor = conn.cursor()

        # 检查表是否已存在
        cursor.execute("""
            SELECT COUNT(*)
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_NAME = 'quality_control_records'
        """)

        if cursor.fetchone()[0] > 0:
            logger.warning("质控表已存在", table="quality_control_records")
            print("⚠️  质控表 'quality_control_records' 已存在")

            # 询问是否删除重建
            response = input("是否删除并重建表？(yes/no): ").strip().lower()
            if response == 'yes':
                cursor.execute("DROP TABLE quality_control_records")
                conn.commit()
                print("✅ 已删除旧表")
            else:
                print("ℹ️  保留现有表，退出")
                cursor.close()
                conn.close()
                return False

        # 创建表
        create_table_sql = """
        CREATE TABLE quality_control_records (
            id BIGINT IDENTITY(1,1) PRIMARY KEY,
            province NVARCHAR(50) NOT NULL,
            city NVARCHAR(50) NOT NULL,
            operation_unit NVARCHAR(100),
            station NVARCHAR(100) NOT NULL,
            start_time DATETIME2 NOT NULL,
            end_time DATETIME2 NOT NULL,
            task_group NVARCHAR(500),
            qc_item NVARCHAR(50) NOT NULL,
            qc_result NVARCHAR(50) NOT NULL,
            response_value DECIMAL(10, 2),
            target_value DECIMAL(10, 2),
            error_value DECIMAL(10, 2),
            molybdenum_efficiency DECIMAL(5, 2),
            warning_limit DECIMAL(10, 2),
            control_limit DECIMAL(10, 2),
            created_at DATETIME2 DEFAULT GETDATE(),
            data_source NVARCHAR(100),
            batch_id UNIQUEIDENTIFIER,

            CONSTRAINT CK_qc_result
                CHECK (qc_result IN ('合格', '超控制限', '超警告限', '钼转换效率偏低'))
        );
        """

        logger.info("执行创建表SQL")
        cursor.execute(create_table_sql)
        conn.commit()

        print("✅ 质控表创建成功")

        # 创建索引
        indexes = [
            ("idx_qc_city", "CREATE NONCLUSTERED INDEX idx_qc_city ON quality_control_records(city)"),
            ("idx_qc_station", "CREATE NONCLUSTERED INDEX idx_qc_station ON quality_control_records(station)"),
            ("idx_qc_item", "CREATE NONCLUSTERED INDEX idx_qc_item ON quality_control_records(qc_item)"),
            ("idx_qc_result", "CREATE NONCLUSTERED INDEX idx_qc_result ON quality_control_records(qc_result)"),
            ("idx_qc_start_time", "CREATE NONCLUSTERED INDEX idx_qc_start_time ON quality_control_records(start_time DESC)"),
            ("idx_qc_operation_unit", "CREATE NONCLUSTERED INDEX idx_qc_operation_unit ON quality_control_records(operation_unit)"),
            ("idx_qc_city_result", "CREATE NONCLUSTERED INDEX idx_qc_city_result ON quality_control_records(city, qc_result)"),
            ("idx_qc_station_time", "CREATE NONCLUSTERED INDEX idx_qc_station_time ON quality_control_records(station, start_time DESC)"),
        ]

        logger.info("创建索引", index_count=len(indexes))

        for index_name, index_sql in indexes:
            try:
                cursor.execute(index_sql)
                conn.commit()
                logger.info("索引创建成功", index=index_name)
            except Exception as e:
                logger.warning("索引创建失败", index=index_name, error=str(e))

        print(f"✅ 索引创建完成（{len(indexes)} 个）")

        # 添加表注释
        try:
            cursor.execute("""
                EXEC sp_addextendedproperty
                @name = N'MS_Description',
                @value = N'质控例行检查记录表',
                @level0type = N'SCHEMA', @level0name = N'dbo',
                @level1type = N'TABLE', @level1name = N'quality_control_records'
            """)
            conn.commit()
        except:
            pass  # 注释可选，失败不影响

        cursor.close()
        conn.close()

        logger.info("质控表创建完成")
        print("\n✅ 质控表创建完成！")
        print("\n表结构：")
        print("  - 主键: id (BIGINT IDENTITY)")
        print("  - 字段: province, city, operation_unit, station, start_time, end_time,")
        print("         task_group, qc_item, qc_result, response_value, target_value,")
        print("         error_value, molybdenum_efficiency, warning_limit, control_limit")
        print("  - 元数据: created_at, data_source, batch_id")
        print("  - 索引: 8 个（优化查询性能）")

        return True

    except Exception as e:
        logger.error("创建质控表失败", error=str(e))
        print(f"❌ 创建质控表失败: {str(e)}")
        return False


if __name__ == "__main__":
    create_quality_control_table()
