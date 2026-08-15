"""
质控例行检查数据导入脚本

读取 /tmp 目录下的例行任务检查文件并导入到 SQL Server 数据库
"""

import sys
from pathlib import Path
import uuid
from datetime import datetime

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pyodbc
import pandas as pd
from config.settings import Settings
import structlog

logger = structlog.get_logger()


def parse_value(value_str):
    """解析带单位的数值（如：'0.74ppb' -> 0.74）"""
    if pd.isna(value_str):
        return None

    if isinstance(value_str, (int, float)):
        return float(value_str)

    # 移除单位（ppb, ppm, %）
    value_str = str(value_str).replace('ppb', '').replace('ppm', '').replace('%', '').strip()

    try:
        return float(value_str)
    except ValueError:
        return None


def import_qc_file(file_path, batch_id, connection_string):
    """导入单个质控检查文件"""

    logger.info("开始导入文件", file=str(file_path))

    try:
        # 读取 Excel 文件
        df = pd.read_excel(file_path)
        logger.info("文件读取成功", row_count=len(df))

        conn = pyodbc.connect(connection_string, timeout=60)
        cursor = conn.cursor()

        imported_count = 0
        failed_count = 0

        # 批量插入（使用 executemany 提高性能）
        insert_data = []

        for idx, row in df.iterrows():
            try:
                # 解析数值字段
                response_value = parse_value(row.get('响应值'))
                target_value = parse_value(row.get('目标值'))
                error_value = parse_value(row.get('误差值'))
                molybdenum_efficiency = parse_value(row.get('钼转换效率'))
                warning_limit = parse_value(row.get('警告限'))
                control_limit = parse_value(row.get('控制限'))

                # 处理质控结果（空值设为"未知"）
                qc_result = row.get('质控结果')
                if pd.isna(qc_result):
                    qc_result = "未知"

                # 构建插入数据
                insert_data.append((
                    row.get('省份'),
                    row.get('城市'),
                    row.get('运维单位') if pd.notna(row.get('运维单位')) else None,
                    row.get('站点'),
                    pd.to_datetime(row.get('开始时间')),
                    pd.to_datetime(row.get('结束时间')),
                    row.get('任务组') if pd.notna(row.get('任务组')) else None,
                    row.get('质控项目'),
                    qc_result,  # 使用处理后的值
                    response_value,
                    target_value,
                    error_value,
                    molybdenum_efficiency,
                    warning_limit,
                    control_limit,
                    Path(file_path).name,
                    str(batch_id)  # 转换为字符串
                ))

                imported_count += 1

            except Exception as e:
                failed_count += 1
                if failed_count <= 5:  # 只打印前5个错误
                    logger.warning(
                        "数据行解析失败",
                        row_index=idx,
                        error=str(e)
                    )

        # 批量插入
        if insert_data:
            insert_sql = """
                INSERT INTO quality_control_records (
                    province, city, operation_unit, station,
                    start_time, end_time, task_group, qc_item, qc_result,
                    response_value, target_value, error_value,
                    molybdenum_efficiency, warning_limit, control_limit,
                    data_source, batch_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """

            cursor.executemany(insert_sql, insert_data)
            conn.commit()

        cursor.close()
        conn.close()

        logger.info(
            "文件导入完成",
            file=str(file_path),
            imported=imported_count,
            failed=failed_count
        )

        return imported_count, failed_count

    except Exception as e:
        logger.error("文件导入失败", file=str(file_path), error=str(e))
        print(f"❌ 文件导入失败 {file_path.name}: {str(e)}")
        return 0, 0


def import_all_qc_files():
    """批量导入所有质控检查文件"""

    settings = Settings()
    connection_string = settings.sqlserver_connection_string

    # 扫描 /tmp 目录
    tmp_dir = Path("/tmp")
    qc_files = list(tmp_dir.glob("例行任务检查*.xls"))

    if not qc_files:
        logger.warning("未找到质控检查文件", directory="/tmp")
        print("⚠️  未找到质控检查文件")
        print(f"   搜索目录: /tmp")
        print(f"   文件模式: 例行任务检查*.xls")
        return

    # 按文件名排序
    qc_files.sort()

    print(f"\n找到 {len(qc_files)} 个质控检查文件\n")

    # 生成批次ID
    batch_id = uuid.uuid4()

    logger.info(
        "开始批量导入",
        file_count=len(qc_files),
        batch_id=str(batch_id)
    )

    total_imported = 0
    total_failed = 0
    success_files = 0

    for i, file_path in enumerate(qc_files, 1):
        file_size = file_path.stat().st_size / 1024  # KB
        print(f"[{i}/{len(qc_files)}] {file_path.name} ({file_size:.1f} KB)", end=" ... ")

        imported, failed = import_qc_file(file_path, batch_id, connection_string)

        if imported > 0:
            print(f"✅ {imported} 条记录")
            success_files += 1
        else:
            print("❌ 失败")

        total_imported += imported
        total_failed += failed

    # 打印汇总
    print("\n" + "="*60)
    print("导入完成")
    print("="*60)
    print(f"文件总数:     {len(qc_files)}")
    print(f"成功文件:     {success_files}")
    print(f"导入记录:     {total_imported} 条")
    print(f"失败记录:     {total_failed} 条")
    print(f"批次ID:       {batch_id}")
    print("="*60)

    # 验证导入结果
    if total_imported > 0:
        conn = pyodbc.connect(connection_string, timeout=10)
        cursor = conn.cursor()

        # 查询总记录数
        cursor.execute("SELECT COUNT(*) FROM quality_control_records")
        total_records = cursor.fetchone()[0]

        # 查询批次记录数
        cursor.execute(
            "SELECT COUNT(*) FROM quality_control_records WHERE batch_id = ?",
            str(batch_id)
        )
        batch_records = cursor.fetchone()[0]

        # 查询城市分布
        cursor.execute("""
            SELECT city, COUNT(*) as count
            FROM quality_control_records
            WHERE batch_id = ?
            GROUP BY city
            ORDER BY count DESC
        """, str(batch_id))

        city_stats = cursor.fetchall()

        cursor.close()
        conn.close()

        print(f"\n验证结果:")
        print(f"  数据库总记录数: {total_records}")
        print(f"  本批次记录数:   {batch_records}")

        if city_stats:
            print(f"\n城市分布（前10个）:")
            for city, count in city_stats[:10]:
                print(f"  {city:12s} {count:4d} 条")

        if batch_records == total_imported:
            print(f"\n✅ 数据验证通过！")
        else:
            print(f"\n⚠️  数据验证异常：导入 {total_imported} 条，但数据库有 {batch_records} 条")

    print()


if __name__ == "__main__":
    import_all_qc_files()
