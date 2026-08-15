"""
质控数据库连接测试脚本

测试内容：
1. 使用现有配置连接 SQL Server
2. 测试数据库权限
3. 验证是否可以创建质控表
4. 测试导入示例数据
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


class QCDatabaseTester:
    """质控数据库连接测试器"""

    def __init__(self):
        """初始化测试器"""
        self.settings = Settings()
        self.connection_string = self.settings.sqlserver_connection_string

    def test_1_basic_connection(self):
        """测试1：基本连接"""
        logger.info("=== 测试1：基本连接测试 ===")

        try:
            conn = pyodbc.connect(self.connection_string, timeout=10)
            cursor = conn.cursor()

            # 查询数据库版本
            cursor.execute("SELECT @@VERSION")
            version = cursor.fetchone()

            # 查询当前数据库名称
            cursor.execute("SELECT DB_NAME()")
            current_db = cursor.fetchone()

            # 查询数据库大小
            cursor.execute("""
                SELECT
                    (SUM(size) * 8 / 1024) AS SizeMB
                FROM sys.master_files
                WHERE DB_NAME(database_id) = ?
            """, current_db[0])
            db_size = cursor.fetchone()

            cursor.close()
            conn.close()

            logger.info(
                "连接成功",
                database=current_db[0],
                size_mb=f"{db_size[0]:.2f} MB",
                version_preview=version[0][:100] if version else None
            )

            print(f"✅ 连接成功！")
            print(f"   数据库: {current_db[0]}")
            print(f"   大小: {db_size[0]:.2f} MB")
            print(f"   版本: {version[0][:80]}...")

            return True

        except Exception as e:
            logger.error("连接失败", error=str(e))
            print(f"❌ 连接失败: {str(e)}")
            return False

    def test_2_check_permissions(self):
        """测试2：检查数据库权限"""
        logger.info("=== 测试2：检查数据库权限 ===")

        try:
            conn = pyodbc.connect(self.connection_string, timeout=10)
            cursor = conn.cursor()

            # 检查 CREATE TABLE 权限
            cursor.execute("SELECT HAS_PERMS_BY_NAME(NULL, 'DATABASE', 'CREATE TABLE')")
            can_create_table = cursor.fetchone()[0]

            # 检查 INSERT 权限
            cursor.execute("SELECT HAS_PERMS_BY_NAME(NULL, 'DATABASE', 'INSERT')")
            can_insert = cursor.fetchone()[0]

            # 检查 SELECT 权限
            cursor.execute("SELECT HAS_PERMS_BY_NAME(NULL, 'DATABASE', 'SELECT')")
            can_select = cursor.fetchone()[0]

            # 查询当前用户
            cursor.execute("SELECT SUSER_NAME()")
            current_user = cursor.fetchone()[0]

            cursor.close()
            conn.close()

            logger.info(
                "权限检查完成",
                user=current_user,
                can_create_table=bool(can_create_table),
                can_insert=bool(can_insert),
                can_select=bool(can_select)
            )

            print(f"✅ 权限检查完成")
            print(f"   当前用户: {current_user}")
            print(f"   CREATE TABLE: {'✅' if can_create_table else '❌'}")
            print(f"   INSERT: {'✅' if can_insert else '❌'}")
            print(f"   SELECT: {'✅' if can_select else '❌'}")

            return {
                'can_create_table': bool(can_create_table),
                'can_insert': bool(can_insert),
                'can_select': bool(can_select),
                'user': current_user
            }

        except Exception as e:
            logger.error("权限检查失败", error=str(e))
            print(f"❌ 权限检查失败: {str(e)}")
            return None

    def test_3_list_existing_tables(self):
        """测试3：列出现有表"""
        logger.info("=== 测试3：列出现有表 ===")

        try:
            conn = pyodbc.connect(self.connection_string, timeout=10)
            cursor = conn.cursor()

            # 查询所有用户表
            cursor.execute("""
                SELECT
                    TABLE_SCHEMA,
                    TABLE_NAME,
                    CREATE_DATE
                FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_TYPE = 'BASE TABLE'
                ORDER BY TABLE_NAME
            """)

            tables = cursor.fetchall()

            cursor.close()
            conn.close()

            logger.info("现有表查询成功", table_count=len(tables))

            print(f"✅ 现有表查询成功")
            print(f"   共 {len(tables)} 个表")

            # 显示前10个表
            if tables:
                print("\n   表列表（前10个）:")
                for i, (schema, name, create_date) in enumerate(tables[:10], 1):
                    print(f"   {i:2}. [{schema}].{name} (创建于 {create_date})")

                if len(tables) > 10:
                    print(f"   ... 还有 {len(tables) - 10} 个表")

            return True

        except Exception as e:
            logger.error("查询现有表失败", error=str(e))
            print(f"❌ 查询现有表失败: {str(e)}")
            return False

    def test_4_check_qc_table_exists(self):
        """测试4：检查质控表是否存在"""
        logger.info("=== 测试4：检查质控表是否存在 ===")

        try:
            conn = pyodbc.connect(self.connection_string, timeout=10)
            cursor = conn.cursor()

            # 检查表是否存在
            cursor.execute("""
                SELECT COUNT(*)
                FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_NAME = 'quality_control_records'
            """)

            count = cursor.fetchone()[0]

            cursor.close()
            conn.close()

            if count > 0:
                logger.info("质控表已存在")
                print(f"✅ 质控表 'quality_control_records' 已存在")

                # 查询表记录数
                conn = pyodbc.connect(self.connection_string, timeout=10)
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM quality_control_records")
                record_count = cursor.fetchone()[0]
                cursor.close()
                conn.close()

                print(f"   当前记录数: {record_count}")
                return True
            else:
                logger.info("质控表不存在")
                print(f"ℹ️  质控表 'quality_control_records' 不存在")
                return False

        except Exception as e:
            logger.error("检查质控表失败", error=str(e))
            print(f"❌ 检查质控表失败: {str(e)}")
            return None

    def test_5_create_test_table(self):
        """测试5：创建测试表（验证权限）"""
        logger.info("=== 测试5：创建测试表 ===")

        try:
            conn = pyodbc.connect(self.connection_string, timeout=10)
            cursor = conn.cursor()

            # 创建测试表
            test_table_sql = """
            CREATE TABLE quality_control_records_test (
                id BIGINT IDENTITY(1,1) PRIMARY KEY,
                province NVARCHAR(50) NOT NULL,
                city NVARCHAR(50) NOT NULL,
                station NVARCHAR(100) NOT NULL,
                qc_item NVARCHAR(50) NOT NULL,
                qc_result NVARCHAR(50) NOT NULL,
                test_timestamp DATETIME2 DEFAULT GETDATE()
            )
            """

            cursor.execute(test_table_sql)
            conn.commit()

            # 插入测试数据
            insert_sql = """
            INSERT INTO quality_control_records_test
            (province, city, station, qc_item, qc_result)
            VALUES (?, ?, ?, ?, ?)
            """

            test_data = (
                "广东省",
                "广州市",
                "测试站点",
                "NO_零点检查",
                "合格"
            )

            cursor.execute(insert_sql, test_data)
            conn.commit()

            # 查询测试数据
            cursor.execute("SELECT COUNT(*) FROM quality_control_records_test")
            count = cursor.fetchone()[0]

            # 删除测试表
            cursor.execute("DROP TABLE quality_control_records_test")
            conn.commit()

            cursor.close()
            conn.close()

            logger.info("测试表创建成功", test_record_count=count)

            print(f"✅ 测试表创建成功")
            print(f"   测试插入记录数: {count}")
            print(f"   测试表已清理")

            return True

        except Exception as e:
            logger.error("创建测试表失败", error=str(e))
            print(f"❌ 创建测试表失败: {str(e)}")

            # 尝试清理
            try:
                conn = pyodbc.connect(self.connection_string, timeout=10)
                cursor = conn.cursor()
                cursor.execute("DROP TABLE quality_control_records_test")
                conn.commit()
                cursor.close()
                conn.close()
            except:
                pass

            return False

    def run_all_tests(self):
        """运行所有测试"""
        print("\n" + "="*60)
        print("质控数据库连接测试")
        print("="*60 + "\n")

        results = {}

        # 测试1：基本连接
        results['connection'] = self.test_1_basic_connection()
        if not results['connection']:
            print("\n❌ 基本连接失败，终止测试")
            return results

        print()

        # 测试2：权限检查
        results['permissions'] = self.test_2_check_permissions()
        if not results['permissions']:
            print("\n⚠️  权限检查失败，继续测试")

        print()

        # 测试3：现有表
        results['list_tables'] = self.test_3_list_existing_tables()

        print()

        # 测试4：质控表是否存在
        results['qc_table_exists'] = self.test_4_check_qc_table_exists()

        print()

        # 测试5：创建测试表
        if results['permissions'] and results['permissions'].get('can_create_table'):
            results['create_table'] = self.test_5_create_test_table()
        else:
            print("⏭️  跳过测试5（无 CREATE TABLE 权限）")
            results['create_table'] = None

        print("\n" + "="*60)
        print("测试总结")
        print("="*60)

        print(f"基本连接: {'✅' if results['connection'] else '❌'}")

        if results.get('permissions'):
            print(f"数据库权限: {'✅' if all(results['permissions'].values()) else '⚠️  部分权限缺失'}")

        print(f"查询现有表: {'✅' if results['list_tables'] else '❌'}")
        print(f"质控表状态: {'✅ 已存在' if results['qc_table_exists'] else 'ℹ️  不存在'}")

        if results.get('create_table'):
            print(f"创建表权限: {'✅' if results['create_table'] else '❌'}")
        elif results.get('permissions'):
            print(f"创建表权限: ❌ (无权限)")

        print("\n" + "="*60)

        # 评估是否可以进行质控表创建
        can_proceed = (
            results['connection'] and
            results.get('permissions', {}).get('can_create_table') and
            results.get('create_table')
        )

        if can_proceed:
            print("✅ 数据库验证通过，可以创建质控表！")
            print("\n下一步操作：")
            print("1. 创建质控表结构（运行 SQL 脚本）")
            print("2. 导入历史数据（运行导入脚本）")
            print("3. 开发查询工具（集成到 Agent）")
        elif results['connection'] and not results.get('qc_table_exists'):
            print("⚠️  数据库连接正常，但无 CREATE TABLE 权限")
            print("\n建议操作：")
            print("1. 联系数据库管理员授予 CREATE TABLE 权限")
            print("2. 或请管理员直接创建质控表")
        elif results['qc_table_exists']:
            print("✅ 质控表已存在，可以直接使用！")
            print("\n下一步操作：")
            print("1. 开发查询工具（集成到 Agent）")
            print("2. 测试查询功能")

        print("="*60 + "\n")

        return results


def main():
    """主函数"""
    tester = QCDatabaseTester()
    results = tester.run_all_tests()


if __name__ == "__main__":
    main()
