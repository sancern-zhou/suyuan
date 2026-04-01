# 运维工单查询工具使用文档

## 概述

运维工单查询工具用于从SQL Server数据库查询运维工单数据，支持多维度筛选和聚合统计分析。

**数据源**：CSV文件导入到SQL Server数据库
**数据库**：AirPollutionAnalysis
**表名**：working_orders

---

## 快速开始

### 1. 数据导入

```bash
cd backend
python -m scripts.import_working_orders
```

### 2. 测试查询

```bash
python -m scripts.test_working_orders_query
```

---

## 数据库表结构

### 表信息
- **表名**：`dbo.working_orders`
- **主键**：`WORKINGORDERID`
- **记录数**：10,533条（截至2026-03-31）

### 核心字段

| 字段名 | 类型 | 说明 | 示例 |
|--------|------|------|------|
| WORKINGORDERID | INT | 工单ID（主键） | 258213 |
| STATIONID | NVARCHAR(50) | 站点ID | "1", "21" |
| DEVICEID | NVARCHAR(MAX) | 设备ID | "2,3,4,9" |
| CREATETIME | DATETIME2 | 创建时间 | 2026-01-01 00:21:04 |
| FINISHTIME | DATETIME2 | 完成时间 | 2026-01-01 09:26:35 |
| DDWORKINGORDERTYPE | NVARCHAR(50) | 工单类型 | Check, Fault, QCBlackOut |
| DDWORKINGORDERSTATUS | NVARCHAR(50) | 工单状态 | Finish, Doing, Wait |
| DDURGENCYTYPE | NVARCHAR(50) | 紧急程度 | Urgent, Middle, Normal |
| MAINTENANCETYPE | NVARCHAR(50) | 维护周期 | Day, Week, Month |
| TOTALOVERTIME | DECIMAL(18,2) | 总超时时间 | 0.00 |

### 工单类型说明

| 类型代码 | 类型名称 | 说明 |
|----------|----------|------|
| Check | 检查 | 常规检查 |
| SupCheck | 超级检查 | 上级检查 |
| Fault | 故障 | 设备故障 |
| QCBlackOut | 质控 | 质控相关 |
| SupSECCheck | SEC检查 | SEC上级检查 |
| Performance | 性能 | 性能相关 |

### 工单状态说明

| 状态代码 | 状态名称 |
|----------|----------|
| Finish | 已完成 |
| Doing | 进行中 |
| Wait | 待办 |
| ToAssign | 待分配 |
| Invalid | 无效 |

---

## CSV数据导入操作

### 准备工作

1. **确认CSV文件路径**
   ```
   D:/溯源/backend_data/MTC_WORKINGORDER_YYYYMMDDHHMMSS.csv
   ```

2. **确认数据库连接**
   - 主机：180.184.30.94:1433
   - 数据库：AirPollutionAnalysis
   - 用户：sa

### 导入步骤

#### 方法1：使用Python脚本（推荐）

```bash
cd backend
python -m scripts.import_working_orders
```

**选项**：
- 指定CSV文件路径：
  ```bash
  python -m scripts.import_working_orders /path/to/your/file.csv
  ```

- 清空表重新导入（修改脚本中 `truncate_first=True`）：

#### 方法2：手动创建表后导入

如果表不存在，先创建表：

```bash
python -m scripts.create_working_orders_table
```

或重新创建表（删除旧表）：

```bash
python -m scripts.recreate_working_orders_table
```

然后执行导入。

### 导入过程

导入脚本会显示进度：

```
[INFO] 开始导入运维工单数据
[INFO] 已导入 1000 条记录
[INFO] 已导入 2000 条记录
...
[INFO] 已导入 10533 条记录
```

### 导入后验证

导入完成后会显示统计信息：

```
============================================================
导入成功!
============================================================
导入记录数: 10533
表总记录数: 10533

数据统计:
------------------------------------------------------------
总记录数: 10533
时间范围: 2026-01-01 00:21:04 ~ 2026-03-31 10:34:54

工单类型统计:
  Check: 4766
  SupCheck: 3604
  Fault: 1089
  ...
```

---

## 常见问题排查

### 问题1：表不存在

**错误信息**：
```
Invalid object name 'dbo.working_orders'
```

**解决方案**：
```bash
python -m scripts.create_working_orders_table
```

### 问题2：字段长度不够

**错误信息**：
```
String or binary data would be truncated
```

**解决方案**：
```bash
python -m scripts.recreate_working_orders_table
```

### 问题3：数据类型转换失败

**错误信息**：
```
Conversion failed when converting the nvarchar value '0.0' to data type bit
```

**解决方案**：
检查 `scripts/import_working_orders.py` 中的数据类型转换逻辑，确保：
- 布尔值字段支持 "0.0"/"1.0" 格式
- 日期时间字段格式正确

### 问题4：连接数据库失败

**错误信息**：
```
Login failed for user 'sa'
```

**解决方案**：
检查 `config/settings.py` 中的数据库配置：
- `sqlserver_host`
- `sqlserver_port`
- `sqlserver_database`
- `sqlserver_user`
- `sqlserver_password`

---

## 查询工具使用

### 基本查询

```python
from app.tools.query.get_working_orders.tool import GetWorkingOrdersTool

tool = GetWorkingOrdersTool()

# 查询前10条记录
result = await tool.execute(limit=10)
```

### 按条件筛选

```python
# 查询未完成的工单
result = await tool.execute(status="Doing", limit=10)

# 查询故障工单
result = await tool.execute(order_type="Fault", limit=10)

# 按时间范围查询
result = await tool.execute(
    start_date="2026-01-01",
    end_date="2026-01-31",
    limit=10
)
```

### 聚合统计

```python
# 按工单类型统计
result = await tool.execute(aggregate_by="order_type")

# 按状态统计
result = await tool.execute(aggregate_by="status")

# 按紧急程度统计
result = await tool.execute(aggregate_by="urgency_type")
```

### 返回格式

```python
{
    "success": True,
    "data": [...],  # 记录列表或聚合结果
    "summary": "查询到 10 条工单"
}
```

---

## 工具文件说明

### 查询工具文件

| 文件 | 说明 |
|------|------|
| `tool.py` | 主查询工具类 |
| `__init__.py` | 模块导出 |
| `README.md` | 本文档 |

### 数据导入脚本

| 文件 | 说明 |
|------|------|
| `scripts/create_working_orders_table.py` | 创建表（如果不存在） |
| `scripts/recreate_working_orders_table.py` | 重新创建表（删除旧表） |
| `scripts/import_working_orders.py` | CSV数据导入 |
| `scripts/test_working_orders_query.py` | 查询工具测试 |
| `scripts/check_table.py` | 检查表是否存在 |

### SQL脚本

| 文件 | 说明 |
|------|------|
| `sql/import_working_orders.sql` | 创建表SQL脚本 |

---

## 数据维护

### 定期导入新数据

建议定期执行数据导入：

```bash
# 每周执行一次
cd backend
python -m scripts.import_working_orders
```

### 数据清理

如需清空表重新导入：

```python
import pyodbc
from config.settings import Settings

settings = Settings()
conn = pyodbc.connect(settings.sqlserver_connection_string)
cursor = conn.cursor()

cursor.execute('TRUNCATE TABLE [dbo].[working_orders]')
conn.commit()

cursor.close()
conn.close()
```

### 备份数据

```bash
# 使用SQL Server备份命令
sqlcmd -S 180.184.30.94,1433 -U sa -P "password" -Q "BACKUP DATABASE AirPollutionAnalysis TO DISK = 'C:\backup\working_orders.bak'"
```

---

## 性能优化

### 索引说明

表已创建以下索引：

| 索引名 | 字段 | 用途 |
|--------|------|------|
| idx_stationid | STATIONID | 按站点查询 |
| idx_createtime | CREATETIME | 按创建时间查询 |
| idx_finishtime | FINISHTIME | 按完成时间查询 |
| idx_status | DDWORKINGORDERSTATUS | 按状态查询 |
| idx_type | DDWORKINGORDERTYPE | 按类型查询 |
| idx_maintenance | MAINTENANCETYPE | 按维护周期查询 |

### 查询优化建议

1. **使用时间范围筛选**：减少扫描数据量
2. **使用聚合查询**：大数据量时优先使用聚合统计
3. **限制返回记录数**：使用 `limit` 参数控制返回量

---

## 更新日志

| 日期 | 版本 | 说明 |
|------|------|------|
| 2026-03-31 | 1.0.0 | 初始版本，支持基本查询和聚合统计 |
