"""
清理历史冗余的 current_month 数据

功能：
1. 清理已转换为 monthly 的历史 current_month 数据
2. 只保留当月的 current_month 数据
3. 避免数据冗余和混淆

适用场景：
- 每月1日转换后会自动清理上月的 current_month
- 此脚本用于手动清理历史遗留的冗余数据
"""
import sys
import pyodbc
from datetime import datetime, date

sys.path.insert(0, '/home/xckj/suyuan/backend')

from app.fetchers.city_statistics.province_statistics_fetcher import ProvinceSQLServerClient


def cleanup_historical_current_month(
    connection_string: str,
    table_name: str,
    before_date: date = None,
    dry_run: bool = True
) -> int:
    """
    清理指定日期之前的 current_month 数据

    Args:
        connection_string: 数据库连接字符串
        table_name: 表名（province_statistics_new_standard 或 city_168_statistics_new_standard）
        before_date: 清理此日期之前的数据（默认：上月1日）
        dry_run: True=只统计不删除，False=实际删除

    Returns:
        删除的记录数
    """
    if before_date is None:
        # 默认清理上月及之前的数据
        today = datetime.now().date()
        if today.month == 1:
            before_date = date(today.year - 1, 12, 1)
        else:
            before_date = date(today.year, today.month - 1, 1)

    print(f"\n{'='*80}")
    print(f"清理表：{table_name}")
    print(f"{'='*80}")
    print(f"清理日期：{before_date} 之前的 current_month 数据")
    print(f"模式：{'模拟运行（不删除）' if dry_run else '实际删除'}")

    try:
        conn = pyodbc.connect(connection_string, timeout=30)
        cursor = conn.cursor()

        # 1. 统计要删除的数据
        count_sql = f"""
        SELECT COUNT(*) as count
        FROM {table_name}
        WHERE stat_type = 'current_month' AND stat_date < ?
        """
        cursor.execute(count_sql, [before_date])
        count = cursor.fetchone().count

        if count == 0:
            print(f"✓ 没有需要清理的数据")
            cursor.close()
            conn.close()
            return 0

        # 2. 显示要删除的数据详情
        detail_sql = f"""
        SELECT stat_date, COUNT(*) as record_count
        FROM {table_name}
        WHERE stat_type = 'current_month' AND stat_date < ?
        GROUP BY stat_date
        ORDER BY stat_date
        """
        cursor.execute(detail_sql, [before_date])
        details = cursor.fetchall()

        print(f"\n待清理数据详情：")
        print("-" * 80)
        for row in details:
            print(f"  {row.stat_date}: {row.record_count} 条记录")
        print(f"总计：{count} 条记录")

        # 3. 删除数据（如果不是 dry_run）
        if not dry_run:
            delete_sql = f"""
            DELETE FROM {table_name}
            WHERE stat_type = 'current_month' AND stat_date < ?
            """
            cursor.execute(delete_sql, [before_date])
            deleted_count = cursor.rowcount
            conn.commit()

            print(f"\n✓ 已删除 {deleted_count} 条记录")
        else:
            print(f"\n[模拟运行] 将删除 {count} 条记录（使用 --execute 实际删除）")

        cursor.close()
        conn.close()
        return count

    except Exception as e:
        print(f"\n✗ 清理失败: {str(e)}")
        return 0


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='清理历史冗余的 current_month 数据')
    parser.add_argument('--execute', action='store_true', help='实际执行删除（默认只模拟运行）')
    parser.add_argument('--before-date', type=str, help='清理此日期之前的数据（格式：YYYY-MM-DD）')
    parser.add_argument('--table', choices=['province', 'city', 'all'], default='all',
                       help='清理哪个表（默认：all）')

    args = parser.parse_args()

    # 解析日期
    before_date = None
    if args.before_date:
        try:
            before_date = datetime.strptime(args.before_date, '%Y-%m-%d').date()
        except ValueError:
            print(f"✗ 日期格式错误: {args.before_date}，请使用 YYYY-MM-DD 格式")
            return

    # 获取数据库连接字符串
    sql_client = ProvinceSQLServerClient()
    conn_str = sql_client.connection_string

    # 清理省级统计表
    if args.table in ['province', 'all']:
        cleanup_historical_current_month(
            connection_string=conn_str,
            table_name='province_statistics_new_standard',
            before_date=before_date,
            dry_run=not args.execute
        )

    # 清理城市统计表
    if args.table in ['city', 'all']:
        cleanup_historical_current_month(
            connection_string=conn_str,
            table_name='city_168_statistics_new_standard',
            before_date=before_date,
            dry_run=not args.execute
        )

    if not args.execute:
        print(f"\n{'='*80}")
        print("提示：使用 --execute 参数实际执行删除操作")
        print(f"{'='*80}")


if __name__ == '__main__':
    main()
