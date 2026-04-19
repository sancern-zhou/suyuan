"""
执行数据库迁移：stat_date 从 DATE 改为 VARCHAR(7)

使用 Python + pyodbc 执行，不依赖 sqlcmd 工具
"""
import sys
import pyodbc
from datetime import datetime

sys.path.insert(0, '/home/xckj/suyuan/backend')

from app.fetchers.city_statistics.province_statistics_fetcher import ProvinceSQLServerClient


def execute_migration():
    """执行数据库迁移"""

    print("="*80)
    print("开始迁移 stat_date 字段格式")
    print("="*80)

    sql_client = ProvinceSQLServerClient()
    conn = pyodbc.connect(sql_client.connection_string, timeout=30)
    cursor = conn.cursor()

    try:
        # ====================================================================
        # 步骤1：备份现有数据
        # ====================================================================
        print("\n步骤1：创建备份表...")

        # 检查备份表是否存在
        cursor.execute("""
            SELECT COUNT(*) FROM sys.tables
            WHERE name = 'province_statistics_new_standard_backup'
        """)
        province_backup_exists = cursor.fetchone()[0] > 0

        cursor.execute("""
            SELECT COUNT(*) FROM sys.tables
            WHERE name = 'city_168_statistics_new_standard_backup'
        """)
        city_backup_exists = cursor.fetchone()[0] > 0

        # 备份省级统计表
        if not province_backup_exists:
            cursor.execute("""
                SELECT * INTO province_statistics_new_standard_backup
                FROM province_statistics_new_standard
            """)
            conn.commit()
            print("  ✓ 省级统计表已备份到 province_statistics_new_standard_backup")
        else:
            print("  - 备份表已存在，跳过（省级表）")

        # 备份城市统计表
        if not city_backup_exists:
            cursor.execute("""
                SELECT * INTO city_168_statistics_new_standard_backup
                FROM city_168_statistics_new_standard
            """)
            conn.commit()
            print("  ✓ 城市统计表已备份到 city_168_statistics_new_standard_backup")
        else:
            print("  - 备份表已存在，跳过（城市表）")

        # ====================================================================
        # 步骤2：添加新字段 stat_date_new
        # ====================================================================
        print("\n步骤2：添加新字段 stat_date_new (VARCHAR(7))...")

        # 检查省级统计表字段
        cursor.execute("""
            SELECT COUNT(*) FROM sys.columns
            WHERE object_id = OBJECT_ID('province_statistics_new_standard')
            AND name = 'stat_date_new'
        """)
        if cursor.fetchone()[0] == 0:
            cursor.execute("""
                ALTER TABLE province_statistics_new_standard
                ADD stat_date_new VARCHAR(7)
            """)
            conn.commit()
            print("  ✓ province_statistics_new_standard: stat_date_new 字段已添加")
        else:
            print("  - stat_date_new 字段已存在（省级表）")

        # 检查城市统计表字段
        cursor.execute("""
            SELECT COUNT(*) FROM sys.columns
            WHERE object_id = OBJECT_ID('city_168_statistics_new_standard')
            AND name = 'stat_date_new'
        """)
        if cursor.fetchone()[0] == 0:
            cursor.execute("""
                ALTER TABLE city_168_statistics_new_standard
                ADD stat_date_new VARCHAR(7)
            """)
            conn.commit()
            print("  ✓ city_168_statistics_new_standard: stat_date_new 字段已添加")
        else:
            print("  - stat_date_new 字段已存在（城市表）")

        # ====================================================================
        # 步骤3：转换日期格式并填充到新字段
        # ====================================================================
        print("\n步骤3：转换日期格式 (2026-01-01 → 2026-01)...")

        # 省级统计表
        cursor.execute("""
            UPDATE province_statistics_new_standard
            SET stat_date_new = FORMAT(CAST(stat_date AS DATE), 'yyyy-MM')
            WHERE stat_date_new IS NULL
        """)
        conn.commit()
        cursor.execute("SELECT COUNT(*) FROM province_statistics_new_standard")
        province_count = cursor.fetchone()[0]
        print(f"  ✓ province_statistics_new_standard: 已转换 {province_count} 条记录")

        # 城市统计表
        cursor.execute("""
            UPDATE city_168_statistics_new_standard
            SET stat_date_new = FORMAT(CAST(stat_date AS DATE), 'yyyy-MM')
            WHERE stat_date_new IS NULL
        """)
        conn.commit()
        cursor.execute("SELECT COUNT(*) FROM city_168_statistics_new_standard")
        city_count = cursor.fetchone()[0]
        print(f"  ✓ city_168_statistics_new_standard: 已转换 {city_count} 条记录")

        # ====================================================================
        # 步骤4：删除旧字段并重命名新字段
        # ====================================================================
        print("\n步骤4：替换字段 (删除旧 stat_date, 重命名 stat_date_new → stat_date)...")

        # 省级统计表
        # 4.1 删除旧字段的约束
        cursor.execute("""
            SELECT 'ALTER TABLE province_statistics_new_standard DROP CONSTRAINT ' + name + ';'
            FROM sys.default_constraints
            WHERE parent_object_id = OBJECT_ID('province_statistics_new_standard')
            AND parent_column_id = (
                SELECT column_id FROM sys.columns
                WHERE object_id = OBJECT_ID('province_statistics_new_standard')
                AND name = 'stat_date'
            )
        """)
        constraint_sql = cursor.fetchone()
        if constraint_sql and constraint_sql[0]:
            cursor.execute(constraint_sql[0])
            conn.commit()
            print("  ✓ 已删除旧字段的默认约束（省级表）")

        # 4.2 删除所有包含 stat_date 的索引
        cursor.execute("""
            SELECT name FROM sys.indexes
            WHERE object_id = OBJECT_ID('province_statistics_new_standard')
        """)
        indexes = cursor.fetchall()
        for idx in indexes:
            # 删除所有索引（因为它们可能依赖 stat_date）
            if idx[0] != 'PK__province__xxxx':  # 保留主键
                try:
                    cursor.execute(f"DROP INDEX {idx[0]} ON province_statistics_new_standard")
                    conn.commit()
                    print(f"  ✓ 已删除索引 {idx[0]}（省级表）")
                except:
                    pass

        # 4.3 删除旧字段
        cursor.execute("ALTER TABLE province_statistics_new_standard DROP COLUMN stat_date")
        conn.commit()
        print("  ✓ 已删除旧 stat_date 字段（省级表）")

        # 4.4 重命名新字段
        cursor.execute("EXEC sp_rename 'province_statistics_new_standard.stat_date_new', 'stat_date', 'COLUMN'")
        conn.commit()
        print("  ✓ stat_date_new 已重命名为 stat_date（省级表）")

        # 城市统计表
        # 删除旧字段的约束
        cursor.execute("""
            SELECT 'ALTER TABLE city_168_statistics_new_standard DROP CONSTRAINT ' + name + ';'
            FROM sys.default_constraints
            WHERE parent_object_id = OBJECT_ID('city_168_statistics_new_standard')
            AND parent_column_id = (
                SELECT column_id FROM sys.columns
                WHERE object_id = OBJECT_ID('city_168_statistics_new_standard')
                AND name = 'stat_date'
            )
        """)
        constraint_sql = cursor.fetchone()
        if constraint_sql and constraint_sql[0]:
            cursor.execute(constraint_sql[0])
            conn.commit()
            print("  ✓ 已删除旧字段的默认约束（城市表）")

        # 删除所有包含 stat_date 的索引
        cursor.execute("""
            SELECT name FROM sys.indexes
            WHERE object_id = OBJECT_ID('city_168_statistics_new_standard')
        """)
        indexes = cursor.fetchall()
        for idx in indexes:
            # 删除所有索引（因为它们可能依赖 stat_date）
            try:
                cursor.execute(f"DROP INDEX {idx[0]} ON city_168_statistics_new_standard")
                conn.commit()
                print(f"  ✓ 已删除索引 {idx[0]}（城市表）")
            except:
                pass

        # 删除旧字段
        cursor.execute("ALTER TABLE city_168_statistics_new_standard DROP COLUMN stat_date")
        conn.commit()
        print("  ✓ 已删除旧 stat_date 字段（城市表）")

        # 重命名新字段
        cursor.execute("EXEC sp_rename 'city_168_statistics_new_standard.stat_date_new', 'stat_date', 'COLUMN'")
        conn.commit()
        print("  ✓ stat_date_new 已重命名为 stat_date（城市表）")

        # ====================================================================
        # 步骤5：验证迁移结果
        # ====================================================================
        print("\n步骤5：验证迁移结果...")
        print("\n省级统计表数据示例：")
        print("-" * 80)
        cursor.execute("""
            SELECT
                stat_date,
                stat_type,
                COUNT(*) as record_count
            FROM province_statistics_new_standard
            GROUP BY stat_date, stat_type
            ORDER BY stat_date DESC, stat_type
        """)
        for row in cursor:
            print(f"  {row.stat_date:12} | {row.stat_type:15} | {row.record_count:3} 条记录")

        print("\n城市统计表数据示例：")
        print("-" * 80)
        cursor.execute("""
            SELECT TOP 5
                stat_date,
                stat_type,
                COUNT(*) as record_count
            FROM city_168_statistics_new_standard
            GROUP BY stat_date, stat_type
            ORDER BY stat_date DESC, stat_type
        """)
        for row in cursor:
            print(f"  {row.stat_date:12} | {row.stat_type:15} | {row.record_count:3} 条记录")

        print("\n" + "="*80)
        print("✓ 迁移完成！")
        print("="*80)
        print("  - stat_date 字段类型：VARCHAR(7)")
        print("  - 日期格式：yyyy-MM (如 2026-01)")
        print("="*80)

    except Exception as e:
        conn.rollback()
        print(f"\n✗ 迁移失败: {str(e)}")
        import traceback
        traceback.print_exc()
        raise

    finally:
        cursor.close()
        conn.close()


if __name__ == '__main__':
    execute_migration()
