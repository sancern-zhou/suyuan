# Bash 工具使用文档

## 概述

Bash 工具允许 Agent 安全地执行 Bash 命令，扩展 Agent 的能力边界。

**跨平台支持**：
- **自动命令转换**: Unix 命令自动转换为 Windows 等价命令
- **Linux/macOS**: 执行原生 Unix 命令
- **Windows**: 执行等价命令或 PowerShell 命令
- **无需手动修改**: 同一套命令在所有平台都能运行

## 功能特性

### 1. 文件操作（跨平台）
```python
# Unix 命令会自动转换为 Windows 等价命令
# ls → dir, cat → type, grep → findstr, pwd → cd

# 列出文件
result = await tool.execute(command="ls -la")
# Windows: 自动转换为 dir
# Linux/macOS: 执行 ls -la

# 读取文件
result = await tool.execute(command="cat file.txt")
# Windows: 自动转换为 type file.txt
# Linux/macOS: 执行 cat file.txt

# 搜索文件内容
result = await tool.execute(command="grep 'TODO' app/")
# Windows: 自动转换为 findstr "TODO" app/
# Linux/macOS: 执行 grep 'TODO' app/
```

### 2. 数据处理
```python
# 运行 Python 脚本
result = await tool.execute(
    command="python scripts/process_data.py --input data.csv"
)

# 处理 NetCDF 文件
result = await tool.execute(
    command="ncdump -h data/output.nc"
)
```

### 3. 系统监控
```python
# 检查磁盘空间
result = await tool.execute(command="df -h")

# 检查进程
result = await tool.execute(command="ps aux | grep python")
```

## 安全机制

### 1. 危险命令黑名单
以下命令被禁止执行：
- `rm -rf /` - 危险删除
- `sudo` / `su` - 权限提升
- `shutdown` / `reboot` - 系统控制
- `mkfs` - 文件系统格式化
- 其他危险操作

### 2. 工作目录限制
- 只能在项目根目录范围内操作
- 无法访问系统敏感目录
- 路径遍历攻击防护

### 3. 超时保护
- 默认超时：60 秒
- 可自定义超时时间
- 超时自动终止进程

### 4. 输出截断
- 默认限制：50KB
- 防止内存溢出
- 保留截断标记

## 使用示例

### 示例 1: 调用 HYSPLIT 模型
```python
# Agent 可以调用 HYSPLIT 轨迹模型
result = await tool.execute(
    command="hyts_std -Ctrajectory/config.txt",
    timeout=120
)
```

### 示例 2: 批量处理数据
```python
# 批量转换 CSV 到 JSON
result = await tool.execute(
    command="for f in data/*.csv; do python scripts/convert.py $f; done"
)
```

### 示例 3: 系统监控
```python
# 检查磁盘空间
result = await tool.execute(command="df -h")
if result['success']:
    print(result['data']['stdout'])
```

## 在 ReAct Agent 中的使用

### 1. 提示词直接描述（优化方案）
**bash 工具不需要两阶段加载**，直接在系统提示词中描述使用方法，提高效率：

**文件**: `app/agent/prompts/react_prompts.py`

```python
TOOL_DESCRIPTIONS = """
## 可用工具详细说明

### 4. 实用工具

#### bash
执行安全的 Bash 命令（文件操作、数据处理、系统监控）

**参数**:
- command (str): 要执行的 Bash 命令（必需）
- timeout (int, optional): 超时时间（秒），默认60
- working_dir (str, optional): 工作目录（可选），必须在项目范围内

**使用场景**:
- 文件操作: ls, cat, head, grep, find 等查看和处理文件
- 数据处理: Python脚本、gdal、ncdump 等数据处理工具
- 气象模型: HYSPLIT、WRF 等命令行工具调用
- 系统监控: df, du, ps 等系统状态查询

**安全限制**:
- 工作目录限制在项目范围内
- 禁止危险命令（rm -rf /、sudo、shutdown等）
- 默认超时60秒
- 输出限制50KB

**示例**:
```bash
# 查看文件列表
command="ls -la backend_data/"

# 查看文件内容（前100行）
command="head -100 requirements.txt"

# 搜索文件内容
command="grep -r 'TODO' app/"

# 运行Python脚本
command="python scripts/process_data.py --input data.csv"

# 调用HYSPLIT模型
command="hyts_std -Ctrajectory/config.txt"
```
"""
```

### 2. Agent 调用流程
```python
# 用户请求
user_query = "检查 backend_data 目录的磁盘使用情况"

# Agent 分析后决定使用 bash 工具
action = {
    "type": "TOOL_CALL",
    "tool": "bash",
    "args": {
        "command": "du -sh backend_data/",
        "timeout": 30
    }
}

# 执行结果（一步到位，无需两阶段加载）
result = await tool.execute(**action['args'])
```

### 3. 工具摘要
**文件**: `app/agent/tool_adapter.py`

```python
# format_available_tools() 函数的使用说明
result += """**使用说明**:
- 自然语言查询工具（含示例）：直接调用
- 标记 ⚠️ 的工具：必须先查看详细参数说明
- **bash 工具**：已在系统提示词的 TOOL_DESCRIPTIONS 中详细说明，直接调用即可"""
```

### 4. 跨平台命令映射表

| Unix 命令 | Windows 等价命令 | 说明 |
|----------|----------------|------|
| `ls` | `dir` | 列出文件 |
| `ls -la` | `dir` | 详细列表 |
| `cat file` | `type file` | 读取文件 |
| `grep pattern` | `findstr pattern` | 搜索文本 |
| `grep -r pattern` | `findstr /s pattern` | 递归搜索 |
| `pwd` | `cd` | 显示当前目录 |
| `rm file` | `del file` | 删除文件 |
| `rm -rf dir` | `rmdir /s /q dir` | 删除目录 |
| `cp src dst` | `copy src dst` | 复制文件 |
| `mv src dst` | `move src dst` | 移动文件 |
| `head -n file` | PowerShell Get-Content | 读取前N行 |
| `clear` | `cls` | 清屏 |

**注意**：
- Python 脚本、HYSPLIT、WRF 等工具无需转换（跨平台通用）
- 复杂命令使用 PowerShell 实现（如 head）
- 安全检查在转换**之前**执行，防止黑名单绕过

### 5. 为什么不需要两阶段加载？

**对比分析**：

| 工具类型 | 示例 | 参数复杂度 | 是否需要两阶段加载 |
|---------|------|-----------|------------------|
| 简单工具 | search_knowledge_base | 参数直观（1个参数） | ❌ 不需要 |
| bash 工具 | bash | 参数直观（1个必需参数） | ❌ 不需要 |
| 复杂工具 | calculate_pm_pmf | 参数复杂+隐式依赖 | ✅ 需要 |

**原因**：
- bash 工具只有1个必需参数 (`command`)
- 参数格式简单（字符串命令）
- 使用示例清晰（常见 Unix 命令）
- 无需复杂的依赖关系

## 测试

运行测试脚本：
```bash
cd backend
python tests/test_bash_tool.py
```

测试覆盖：
1. 基本命令执行（pwd, ls）
2. 文件操作（cat, head, echo）
3. 安全检查（危险命令拒绝）
4. 超时保护（sleep 命令）
5. 输出截断（长输出）
6. 工具注册验证
7. 工作目录限制

## 注意事项

1. **只用于工具调用**：不要用此工具编写复杂脚本
2. **优先使用现有工具**：如需要数据处理，优先使用专门的 Python 工具
3. **安全第一**：避免执行不可信的命令
4. **资源限制**：注意超时和输出大小限制

## 技术细节

### 类继承
```python
class BashTool(LLMTool):
    def __init__(self):
        super().__init__(
            name="bash",
            description="执行安全的 Bash 命令",
            category=ToolCategory.QUERY,
            version="1.0.0",
            requires_context=False
        )
```

### 注册优先级
- Priority: 500（低优先级，在所有业务工具之后）
- Category: QUERY（查询工具类）

### 与其他项目的对比

| 特性 | openwork-dev | learn-claude-code | 你的项目 |
|------|-------------|------------------|---------|
| 实现 | Rust Command | Python subprocess | Python subprocess |
| 安全 | 基本检查 | 黑名单过滤 | 多层防护 |
| 编码 | UTF-8 | 默认 | UTF-8 + replace |
| 跨平台 | 平台适配器 | Unix-only | Windows/Linux |
