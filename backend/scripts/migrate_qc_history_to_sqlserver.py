#!/usr/bin/env python3
"""
将 qc_history 表从 PostgreSQL 迁移到 SQL Server

步骤:
1. 从 PostgreSQL 读取 qc_history 表结构和数据
2. 在 SQL Server 中创建 qc_history 表
3. 批量导入数据
4. 验证迁移结果
"""

import sys
from pathlib import Path
import asyncio

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncpg
import pyodbc
import pandas as pd
from config.settings import Settings
import structlog
from datetime import datetime
from tqdm import tqdm

logger = structlog.get_logger()


async def get_postgres_connection():
    """获取PostgreSQL连接"""
    import os
    from dotenv import load_dotenv

    load_dotenv()
    database_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:Xc13129092470@180.184.30.94:5432/weather_db")

    # 从 DATABASE_URL 中提取连接参数
    import re
    match = re.match(r'postgresql\+\w+://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)', database_url)

    if match:
        user, password, host, port, database = match.groups()
        return await asyncpg.connect(
            host=host,
            port=int(port),
            user=user,
            password=password,
            database=database
        )
    else:
        raise ValueError(f"Invalid DATABASE_URL format: {database_url}")


def get_sqlserver_connection():
    """获取SQL Server连接"""
    settings = Settings()
    return pyodbc.connect(settings.sqlserver_connection_string, timeout=60)


async def read_qc_history_from_postgres(batch_size=1000):
    """从PostgreSQL分批读取qc_history数据"""
    conn = await get_postgres_connection()

    try:
        # 获取总记录数
        total_count = await conn.fetchval("SELECT COUNT(*) FROM qc_history")
        logger.info("PostgreSQL总记录数", total=total_count)

        # 分批读取数据
        offset = 0
        all_data = []

        with tqdm(total=total_count, desc="读取PostgreSQL数据") as pbar:
            while offset < total_count:
                rows = await conn.fetch(f"""
                    SELECT
                        id,
                        unique_code,
                        station_code,
                        real_start_time,
                        start_time,
                        end_time,
                        create_time,
                        mission_group_name,
                        mission_name,
                        result,
                        target_value,
                        relevant_value,
                        warming_limit,
                        control_limit,
                        inaccuracy,
                        send_field_split,
                        send_field,
                        source,
                        document_name,
                        document_address,
                        imported_at
                    FROM qc_history
                    ORDER BY id
                    LIMIT {batch_size} OFFSET {offset}
                """)

                all_data.extend([dict(row) for row in rows])
                offset += len(rows)
                pbar.update(len(rows))

        logger.info("数据读取完成", record_count=len(all_data))
        return all_data

    finally:
        await conn.close()


def create_qc_history_table_in_sqlserver():
    """在SQL Server中创建qc_history表"""
    conn = get_sqlserver_connection()
    cursor = conn.cursor()

    try:
        # 检查表是否已存在
        cursor.execute("""
            SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_NAME = 'qc_history'
        """)
        exists = cursor.fetchone()[0] > 0

        if exists:
            # 删除旧表
            logger.info("删除已存在的qc_history表")
            cursor.execute("DROP TABLE qc_history")
            conn.commit()

        # 创建表
        create_table_sql = """
        CREATE TABLE qc_history (
            id BIGINT PRIMARY KEY,
            unique_code NVARCHAR(50) NOT NULL,
            station_code NVARCHAR(50) NULL,
            real_start_time DATETIME NULL,
            start_time DATETIME NULL,
            end_time DATETIME NULL,
            create_time DATETIME NULL,
            mission_group_name NVARCHAR(255) NULL,
            mission_name NVARCHAR(255) NULL,
            result NVARCHAR(255) NULL,
            target_value DECIMAL(18, 6) NULL,
            relevant_value DECIMAL(18, 6) NULL,
            warming_limit DECIMAL(18, 6) NULL,
            control_limit DECIMAL(18, 6) NULL,
            inaccuracy DECIMAL(18, 6) NULL,
            send_field_split INT NULL,
            send_field NVARCHAR(MAX) NULL,
            source INT NULL,
            document_name NVARCHAR(255) NULL,
            document_address NVARCHAR(MAX) NULL,
            imported_at DATETIME NULL
        )
        """

        cursor.execute(create_table_sql)
        conn.commit()

        # 创建索引
        logger.info("创建索引")
        cursor.execute("CREATE INDEX idx_qc_history_station_code ON qc_history(station_code)")
        cursor.execute("CREATE INDEX idx_qc_history_start_time ON qc_history(start_time)")
        cursor.execute("CREATE INDEX idx_qc_history_mission_name ON qc_history(mission_name)")
        conn.commit()

        logger.info("qc_history表创建成功")

    finally:
        cursor.close()
        conn.close()


def migrate_data_to_sqlserver(data):
    """将数据迁移到SQL Server"""
    if not data:
        logger.warning("没有数据需要迁移")
        return 0

    conn = get_sqlserver_connection()
    cursor = conn.cursor()

    try:
        # 准备插入SQL
        insert_sql = """
        INSERT INTO qc_history (
            id, unique_code, station_code,
            real_start_time, start_time, end_time, create_time,
            mission_group_name, mission_name, result,
            target_value, relevant_value, warming_limit, control_limit, inaccuracy,
            send_field_split, send_field, source,
            document_name, document_address, imported_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        # 批量插入
        logger.info("开始批量插入数据到SQL Server", record_count=len(data))

        batch_size = 1000
        inserted_count = 0

        with tqdm(total=len(data), desc="写入SQL Server") as pbar:
            for i in range(0, len(data), batch_size):
                batch = data[i:i + batch_size]

                # 准备批次数据
                insert_data = []
                for record in batch:
                    insert_data.append((
                        record['id'],
                        record['unique_code'],
                        record['station_code'],
                        record['real_start_time'],
                        record['start_time'],
                        record['end_time'],
                        record['create_time'],
                        record['mission_group_name'],
                        record['mission_name'],
                        record['result'],
                        record['target_value'],
                        record['relevant_value'],
                        record['warming_limit'],
                        record['control_limit'],
                        record['inaccuracy'],
                        record['send_field_split'],
                        record['send_field'],
                        record['source'],
                        record['document_name'],
                        record['document_address'],
                        record['imported_at']
                    ))

                cursor.executemany(insert_sql, insert_data)
                conn.commit()

                inserted_count += len(batch)
                pbar.update(len(batch))

        logger.info("数据迁移完成", inserted=inserted_count)
        return inserted_count

    except Exception as e:
        conn.rollback()
        logger.error("数据迁移失败", error=str(e))
        raise
    finally:
        cursor.close()
        conn.close()


def verify_migration():
    """验证迁移结果"""
    logger.info("开始验证迁移结果")

    # 连接SQL Server
    conn = get_sqlserver_connection()
    cursor = conn.cursor()

    try:
        # 查询总记录数
        cursor.execute("SELECT COUNT(*) FROM qc_history")
        sqlserver_count = cursor.fetchone()[0]

        # 查询最新数据样例
        cursor.execute("SELECT TOP 5 * FROM qc_history ORDER BY id DESC")
        sample_rows = cursor.fetchall()

        # 获取列名
        cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'qc_history' ORDER BY ORDINAL_POSITION")
        columns = [row[0] for row in cursor.fetchall()]

        logger.info(
            "迁移验证完成",
            sqlserver_record_count=sqlserver_count,
            sample_columns=len(columns)
        )

        return {
            "total_records": sqlserver_count,
            "columns": columns,
            "sample_data": sample_rows
        }

    finally:
        cursor.close()
        conn.close()


async def main():
    """主函数"""
    print("=" * 80)
    print("qc_history 表迁移工具")
    print("从 PostgreSQL (weather_db) -> SQL Server (XcAiDb)")
    print("=" * 80)
    print()

    try:
        # 步骤1：从PostgreSQL读取数据
        print("步骤1：从PostgreSQL读取数据")
        data = await read_qc_history_from_postgres(batch_size=5000)
        print(f"✅ 读取 {len(data)} 条记录\n")

        # 步骤2：在SQL Server中创建表
        print("步骤2：在SQL Server中创建qc_history表")
        create_qc_history_table_in_sqlserver()
        print("✅ 表创建成功\n")

        # 步骤3：迁移数据
        print("步骤3：迁移数据到SQL Server")
        inserted = migrate_data_to_sqlserver(data)
        print(f"✅ 成功迁移 {inserted} 条记录\n")

        # 步骤4：验证
        print("步骤4：验证迁移结果")
        result = verify_migration()
        print(f"✅ SQL Server总记录数: {result['total_records']}")
        print(f"✅ 字段数量: {len(result['columns'])}")
        print()

        # 显示样例数据
        if result['sample_data']:
            print("最新5条记录:")
            for i, row in enumerate(result['sample_data'], 1):
                print(f"  {i}. ID={row[0]}, Station={row[2]}, Mission={row[8]}, Result={row[9]}")

        print()
        print("=" * 80)
        print("✅ 迁移完成！")
        print("=" * 80)

    except Exception as e:
        logger.error("迁移失败", error=str(e))
        print(f"\n❌ 迁移失败: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
