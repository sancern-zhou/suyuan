# 数据库初始化指南

本目录包含大气污染溯源分析系统的数据库初始化脚本和测试工具。

## 📁 文件说明

| 文件名 | 用途 | 平台 |
|--------|------|------|
| `init_history_table_complete.sql` | 完整的数据库初始化SQL脚本 | 所有 |
| `init_database.bat` | Windows一键初始化脚本 | Windows |
| `init_database.sh` | Linux/macOS一键初始化脚本 | Linux/macOS |
| `test_database_connection.py` | Python数据库连接测试脚本 | 所有 |

## 🚀 快速开始

### 方法一：使用一键脚本（推荐）

#### Windows用户：
```bash
# 在 backend/database 目录下执行
cd backend\database
init_database.bat
```

#### Linux/macOS用户：
```bash
# 在 backend/database 目录下执行
cd backend/database
chmod +x init_database.sh
./init_database.sh
```

### 方法二：手动执行SQL脚本

```bash
sqlcmd -S 180.184.30.94 -U sa -P "#Ph981,6J2bOkWYT7p?5slH$I~g_0itR" -i init_history_table_complete.sql
```

## 📋 前置条件

### 1. 安装 SQL Server 命令行工具

#### Windows：
下载并安装 Microsoft ODBC Driver 17 for SQL Server 和 sqlcmd：
- https://docs.microsoft.com/en-us/sql/tools/sqlcmd-utility

#### Linux (Ubuntu/Debian)：
```bash
curl https://packages.microsoft.com/keys/microsoft.asc | sudo apt-key add -
curl https://packages.microsoft.com/config/ubuntu/20.04/prod.list | sudo tee /etc/apt/sources.list.d/mssql-release.list
sudo apt-get update
sudo ACCEPT_EULA=Y apt-get install -y mssql-tools unixodbc-dev
```

#### macOS：
```bash
brew tap microsoft/mssql-release https://github.com/Microsoft/homebrew-mssql-release
brew update
HOMEBREW_NO_ENV_FILTERING=1 ACCEPT_EULA=Y brew install msodbcsql17 mssql-tools
```

### 2. 验证 sqlcmd 安装

```bash
sqlcmd -?
```

如果显示帮助信息，说明安装成功。

## 🔍 脚本功能说明

### `init_history_table_complete.sql`

此脚本会自动执行以下操作：

1. ✅ **检查并创建数据库** `AirPollutionAnalysis`
2. ✅ **创建主表** `analysis_history`（包含30+字段）
3. ✅ **创建索引**（5个性能优化索引）
4. ✅ **添加约束**（数据完整性检查）
5. ✅ **验证表结构**（自动检查列数、索引数）
6. ✅ **显示表结构概览**

### 表结构概述

`analysis_history` 表包含以下主要字段分组：

- **标识符**: `id`, `session_id`
- **查询信息**: `query_text`, `scale`, `location`, `city`, `pollutant`, `start_time`, `end_time`
- **原始数据** (JSON): `meteorological_data`, `monitoring_data`, `vocs_data`, `particulate_data`, `upwind_enterprises`
- **分析结果** (JSON): `weather_analysis`, `regional_comparison`, `comprehensive_summary`, `kpi_data`, `modules_data`
- **对话历史**: `chat_messages`
- **元数据**: `status`, `duration_seconds`, `created_at`, `is_bookmarked`, `notes`

## ✅ 验证安装

### 步骤1：执行初始化脚本

运行上述一键脚本或手动执行SQL。

### 步骤2：检查日志

查看生成的 `init_output.log` 文件，确认没有错误：

```bash
cat init_output.log  # Linux/macOS
type init_output.log  # Windows
```

预期输出应包含：
- ✓ 数据库创建成功
- ✓ 表创建成功
- ✓ 创建索引: idx_created_at
- ✓ 创建索引: idx_city_pollutant
- ...

### 步骤3：运行Python测试

```bash
# 确保在 backend/database 目录下
cd backend/database

# 安装依赖（如果尚未安装）
pip install pyodbc aioodbc

# 运行测试脚本
python test_database_connection.py
```

测试脚本会验证：
- ✅ 数据库连接
- ✅ 表结构正确性
- ✅ 索引存在
- ✅ CRUD操作（创建、读取、更新、删除）

## 🔧 配置后端

初始化完成后，确保 `backend/.env` 文件包含正确的配置：

```env
# SQL Server Configuration
SQLSERVER_HOST=180.184.30.94
SQLSERVER_PORT=1433
SQLSERVER_DATABASE=AirPollutionAnalysis
SQLSERVER_USER=sa
SQLSERVER_PASSWORD=#Ph981,6J2bOkWYT7p?5slH$I~g_0itR
SQLSERVER_DRIVER=ODBC Driver 17 for SQL Server
```

## 🐛 故障排查

### 问题1：连接超时

**症状**：`Timeout expired` 或 `Cannot open server`

**解决方案**：
1. 检查网络连接到 180.184.30.94
2. 验证SQL Server端口1433开放
3. 测试连接：`telnet 180.184.30.94 1433`

### 问题2：认证失败

**症状**：`Login failed for user 'sa'`

**解决方案**：
1. 确认密码正确（注意特殊字符）
2. 检查SQL Server是否启用了SQL Server身份验证
3. 验证sa账户未被禁用

### 问题3：ODBC驱动未找到

**症状**：`pyodbc.Error: ('01000', "[01000] [unixODBC][Driver Manager]Can't open lib...`

**解决方案**：
```bash
# 查看已安装的驱动
odbcinst -q -d

# 如果没有显示 ODBC Driver 17 for SQL Server，重新安装
# Windows: 下载安装包
# Linux: sudo apt-get install msodbcsql17
# macOS: brew install msodbcsql17
```

### 问题4：表已存在

**症状**：`There is already an object named 'analysis_history'`

**解决方案**：
这是正常的！脚本会自动跳过已存在的表。如果需要重建表：

```sql
-- 手动删除旧表（谨慎！会丢失所有数据）
USE AirPollutionAnalysis;
DROP TABLE IF EXISTS dbo.analysis_history;
GO

-- 然后重新运行初始化脚本
```

## 📊 查看数据

### 使用 sqlcmd 查询：

```bash
sqlcmd -S 180.184.30.94 -U sa -P "#Ph981,6J2bOkWYT7p?5slH$I~g_0itR" -d AirPollutionAnalysis -Q "SELECT TOP 10 session_id, query_text, city, pollutant, created_at FROM analysis_history ORDER BY created_at DESC"
```

### 使用 SQL Server Management Studio (SSMS)：

1. 连接到 `180.184.30.94`
2. 使用 sa 账户登录
3. 展开 `AirPollutionAnalysis` → `Tables` → `dbo.analysis_history`
4. 右键 → 选择 "Select Top 1000 Rows"

## 🎯 下一步

数据库初始化完成后：

1. ✅ 启动后端服务
   ```bash
   cd backend
   python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

2. ✅ 测试历史API
   ```bash
   curl http://localhost:8000/api/history/list
   ```

3. ✅ 集成前端HistoryDrawer组件
   参考 `HISTORY_FEATURE_GUIDE.md` 第三节

## 📚 相关文档

- **完整集成指南**: `../../HISTORY_FEATURE_GUIDE.md`
- **API文档**: 启动后端后访问 `http://localhost:8000/docs`
- **项目文档**: `../../CLAUDE.md`

## 💡 提示

- 初始化脚本是**幂等的**，可以多次执行而不会破坏现有数据
- 生产环境部署前，建议先在测试环境验证
- 定期备份数据库（建议每天）
- 监控数据库大小，根据需要调整保留策略

---

**如有问题，请查看 `HISTORY_FEATURE_GUIDE.md` 的故障排查章节。**
