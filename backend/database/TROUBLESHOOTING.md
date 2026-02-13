# 数据库连接故障排查指南

## 🔴 问题诊断

您遇到的错误是：
```
Login failed for user 'sa'. (18456)
无效的连接字符串属性
```

**根本原因**：密码包含特殊字符（`#`, `?`, `$`, `,`, `~`），在ODBC连接字符串中未正确转义。

## ✅ 已修复的问题

### 1. **连接字符串密码转义**

**位置**: `backend/config/settings.py:194`

**修改前**:
```python
f"PWD={self.sqlserver_password};"
```

**修改后**:
```python
f"PWD={{{self.sqlserver_password}}};"  # 用大括号包裹密码
```

**说明**: ODBC连接字符串中，包含特殊字符的值必须用大括号 `{}` 包裹。

### 2. **批处理脚本中文乱码**

**文件**: `backend/database/init_database.bat`

**修改**: 移除所有中文文本，使用英文替代，避免编码问题。

## 🧪 验证修复

### 步骤1：快速测试连接

```bash
cd backend\database
python quick_test.py
```

这个脚本会：
- ✅ 显示连接字符串配置
- ✅ 检查ODBC驱动
- ✅ 测试数据库连接
- ✅ 检查表是否存在

**预期输出**:
```
[SUCCESS] Connection established!
SQL Server version: Microsoft SQL Server 2019...
Current database: AirPollutionAnalysis
```

### 步骤2：重新运行初始化脚本

```bash
cd backend\database
init_database.bat
```

### 步骤3：完整功能测试

```bash
cd backend\database
python test_database_connection.py
```

**预期输出**:
```
============================================================
测试结果汇总
============================================================
Connection           ✅ 通过
Structure            ✅ 通过
Indexes              ✅ 通过
Crud                 ✅ 通过
============================================================
```

## 📋 完整解决方案步骤

### 方案A：使用修复后的脚本（推荐）

1. **确认修复已应用**
   ```bash
   # 查看settings.py是否已更新（第194行应该有大括号）
   ```

2. **运行快速测试**
   ```bash
   cd backend\database
   python quick_test.py
   ```

3. **如果连接成功，运行初始化脚本**
   ```bash
   init_database.bat
   ```

4. **运行完整测试**
   ```bash
   python test_database_connection.py
   ```

### 方案B：手动验证和修复

1. **检查.env文件**
   ```bash
   # 确认密码正确（不要有多余的引号）
   SQLSERVER_PASSWORD=#Ph981,6J2bOkWYT7p?5slH$I~g_0itR
   ```

2. **验证Python代码变更**
   打开 `backend/config/settings.py`，找到第194行，确认是：
   ```python
   f"PWD={{{self.sqlserver_password}}};"
   ```

3. **测试连接字符串**
   ```python
   # 在Python中测试
   from config.settings import settings
   print(settings.sqlserver_connection_string)

   # 应该看到：
   # PWD={#Ph981,6J2bOkWYT7p?5slH$I~g_0itR};
   #     ^                                ^
   #     注意密码两边的大括号
   ```

## 🔍 常见错误对照表

| 错误信息 | 原因 | 解决方案 |
|---------|------|---------|
| `Login failed for user 'sa'` | 密码错误或未正确转义 | 用大括号包裹密码 |
| `无效的连接字符串属性` | 特殊字符未转义 | 用大括号包裹密码 |
| `Cannot find object 'dbo.analysis_history'` | 表未创建 | 运行初始化脚本 |
| `ODBC Driver not found` | 驱动未安装 | 安装ODBC Driver 17 |
| `Timeout expired` | 网络不通 | 检查防火墙和网络 |

## 🛠️ 进一步排查

### 如果快速测试仍然失败：

1. **验证网络连接**
   ```bash
   ping 180.184.30.94
   telnet 180.184.30.94 1433
   ```

2. **检查ODBC驱动**
   ```bash
   # PowerShell
   Get-OdbcDriver | Where-Object {$_.Name -like "*SQL Server*"}

   # 或运行
   odbcad32.exe
   # 查看"驱动程序"选项卡
   ```

3. **测试sqlcmd直接连接**
   ```bash
   sqlcmd -S 180.184.30.94 -U sa -P "#Ph981,6J2bOkWYT7p?5slH$I~g_0itR" -Q "SELECT @@VERSION"
   ```

4. **检查SQL Server日志**
   - 在SQL Server Management Studio中查看错误日志
   - 查找18456错误的详细信息

### 如果密码包含特殊字符：

**特殊字符列表**（需要用大括号包裹）：
- `#` - 注释符
- `?` - 通配符
- `$` - 变量标识
- `;` - 分隔符
- `=` - 赋值符
- `{` `}` - 大括号本身
- 空格

**示例**：
```python
# 错误的方式
PWD=my#pass$word

# 正确的方式
PWD={my#pass$word}
```

## 📞 获取帮助

如果问题仍未解决：

1. **收集诊断信息**
   ```bash
   python quick_test.py > diagnostic.log 2>&1
   ```

2. **检查日志文件**
   - `init_output.log` - 数据库初始化日志
   - `diagnostic.log` - 连接测试诊断

3. **提供以下信息**
   - Python版本：`python --version`
   - pyodbc版本：`pip show pyodbc`
   - ODBC驱动列表
   - 错误的完整堆栈跟踪

## ✅ 验证清单

完成以下检查确保一切正常：

- [ ] `settings.py` 第194行包含 `PWD={{{self.sqlserver_password}}};`
- [ ] `.env` 文件中密码正确且无多余引号
- [ ] `python quick_test.py` 显示 `[SUCCESS]`
- [ ] `init_database.bat` 执行成功
- [ ] `test_database_connection.py` 所有测试通过
- [ ] 表 `analysis_history` 已创建
- [ ] 索引已创建（5个）

---

**完成所有步骤后，您的数据库应该已经准备就绪！** 🎉
