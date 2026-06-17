-- 解决工单标题和内容编码问题的SQL方案

-- 方案1：修复现有列的排序规则（推荐）
-- 注意：这会重建表，需要停机操作

USE AirPollutionAnalysis;
GO

-- 1.1 创建新的临时列（使用正确的排序规则）
ALTER TABLE dbo.working_orders
ADD ORDERTITLE_NEW NVARCHAR(MAX) COLLATE Chinese_PRC_CI_AS NULL,
    ORDERCONTENT_NEW NVARCHAR(MAX) COLLATE Chinese_PRC_CI_AS NULL,
    StationName_NEW NVARCHAR(100) COLLATE Chinese_PRC_CI_AS NULL;
GO

-- 1.2 尝试恢复数据（如果有备份的话，这步可以跳过）
-- 如果有原始数据源，从源重新导入数据

-- 1.3 删除旧列
ALTER TABLE dbo.working_orders
DROP COLUMN ORDERTITLE, ORDERCONTENT, StationName;
GO

-- 1.4 重命名新列
EXEC sp_rename 'dbo.working_orders.ORDERTITLE_NEW', 'ORDERTITLE', 'COLUMN';
EXEC sp_rename 'dbo.working_orders.ORDERCONTENT_NEW', 'ORDERCONTENT', 'COLUMN';
EXEC sp_rename 'dbo.working_orders.StationName_NEW', 'StationName', 'COLUMN';
GO

-- 方案2：修改数据库默认排序规则（需要重建数据库）
-- 这是最彻底的解决方案，但需要大量工作

-- 查看当前数据库排序规则
SELECT name, collation_name FROM sys.databases WHERE name = 'AirPollutionAnalysis';

-- 方案3：应用程序层修复（临时方案）
-- 在查询时使用COLLATE子句

SELECT
    WORKINGORDERCODE,
    ORDERTITLE COLLATE Chinese_PRC_CI_AS as ORDERTITLE,
    ORDERCONTENT COLLATE Chinese_PRC_CI_AS as ORDERCONTENT,
    StationName COLLATE Chinese_PRC_CI_AS as StationName
FROM dbo.working_orders;

-- 方案4：修改pyodbc连接字符串（治标不治本）
-- 这不会修复已损坏的数据，只能防止未来的问题
-- 在settings.py中添加连接参数
