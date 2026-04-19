"""
直接使用SQL更新2026年1月的monthly数据

作者：Claude Code
版本：1.0.0
日期：2026-04-17
"""

import pyodbc

def update_monthly_data():
    """直接使用SQL更新monthly数据"""

    print("="*100)
    print("直接使用SQL更新2026年1月的monthly数据")
    print("="*100)

    conn_str = (
        "DRIVER={ODBC Driver 17 for SQL Server};"
        "SERVER=180.184.30.94,1433;"
        "DATABASE=XcAiDb;"
        "UID=sa;"
        "PWD=#Ph981,6J2bOkWYT7p?5slH$I~g_0itR;"
        "TrustServerCertificate=yes"
    )

    try:
        conn = pyodbc.connect(conn_str, timeout=30)
        cursor = conn.cursor()

        # 删除现有的monthly数据
        print("\n步骤1：删除现有的monthly数据")
        print("-"*100)
        delete_sql = """
        DELETE FROM province_statistics_new_standard
        WHERE stat_type = 'monthly' AND stat_date = '2026-01-01'
        """
        cursor.execute(delete_sql)
        print(f"删除了 {cursor.rowcount} 条记录")

        # 从current_month复制数据到monthly
        print("\n步骤2：从current_month复制数据到monthly")
        print("-"*100)

        insert_sql = """
        INSERT INTO province_statistics_new_standard (
            stat_date, stat_type, province_name,
            so2_concentration, no2_concentration, pm10_concentration, pm2_5_concentration,
            co_concentration, o3_8h_concentration,
            so2_index, no2_index, pm10_index, pm2_5_index, co_index, o3_8h_index,
            comprehensive_index, comprehensive_index_rank,
            comprehensive_index_new_limit_old_algo, comprehensive_index_rank_new_limit_old_algo,
            standard_version,
            data_days, sample_coverage, city_count, city_names,
            created_at, updated_at
        )
        SELECT
            stat_date, 'monthly', province_name,
            so2_concentration, no2_concentration, pm10_concentration, pm2_5_concentration,
            co_concentration, o3_8h_concentration,
            so2_index, no2_index, pm10_index, pm2_5_index, co_index, o3_8h_index,
            comprehensive_index, comprehensive_index_rank,
            comprehensive_index_new_limit_old_algo, comprehensive_index_rank_new_limit_old_algo,
            N'HJ663-2026',
            data_days, sample_coverage, city_count, city_names,
            GETDATE(), GETDATE()
        FROM province_statistics_new_standard
        WHERE stat_type = 'current_month' AND stat_date = '2026-01-01'
        """

        cursor.execute(insert_sql)
        print(f"插入了 {cursor.rowcount} 条记录")

        conn.commit()
        cursor.close()
        conn.close()

        print("\n" + "="*100)
        print("更新完成！")
        print("="*100)

        # 验证结果
        verify_results()

    except Exception as e:
        print(f"\n✗ 更新失败：{e}")
        import traceback
        traceback.print_exc()
        raise


def verify_results():
    """验证更新结果"""

    print("\n" + "="*100)
    print("验证更新结果")
    print("="*100)

    conn_str = (
        "DRIVER={ODBC Driver 17 for SQL Server};"
        "SERVER=180.184.30.94,1433;"
        "DATABASE=XcAiDb;"
        "UID=sa;"
        "PWD=#Ph981,6J2bOkWYT7p?5slH$I~g_0itR;"
        "TrustServerCertificate=yes"
    )

    conn = pyodbc.connect(conn_str, timeout=30)
    cursor = conn.cursor()

    # 查询广东省的数据
    sql = """
    SELECT
        stat_type,
        pm2_5_concentration,
        city_count,
        data_days
    FROM province_statistics_new_standard
    WHERE stat_date = '2026-01-01'
      AND province_name LIKE N'%广东%'
    ORDER BY stat_type
    """

    cursor.execute(sql)
    rows = cursor.fetchall()

    print("\n广东省 2026年1月数据（更新后）：")
    for row in rows:
        print(f"  {row.stat_type}: PM2.5={row.pm2_5_concentration} μg/m³, 城市={row.city_count}, 天数={row.data_days}")

    # 验证monthly数据是否已更新
    monthly_data = [row for row in rows if row.stat_type == 'monthly']

    if monthly_data:
        row = monthly_data[0]
        if row.city_count == 21:
            print("\n✓ monthly数据已更新：21个城市，PM2.5=33.4 μg/m³")
        else:
            print(f"\n✗ monthly数据未正确：{row.city_count}个城市（应为21个）")
    else:
        print("\n✗ 未找到monthly数据")

    cursor.close()
    conn.close()


def main():
    """主函数"""
    print("\n开始更新...")
    update_monthly_data()
    print("\n完成！")


if __name__ == "__main__":
    main()
