# 中文字体配置完整指南

## 问题说明

在 Linux 系统上，matplotlib 默认使用的字体（如 DejaVu Sans）不支持中文，会导致：
- 中文字符显示为方框 ▯▯▯
- 某些数字字符无法显示
- 图表标题、标签乱码

## 解决方案

### 方案 1：安装系统字体（推荐）

#### Ubuntu/Debian 系统
```bash
# 安装 Noto CJK 字体（Google 开源，支持中日韩）
sudo apt update
sudo apt install fonts-noto-cjk

# 或安装文泉驿字体
sudo apt install fonts-wqy-microhei
sudo apt install fonts-wqy-zenhei
```

#### CentOS/RHEL 系统
```bash
# 安装 Noto CJK 字体
sudo yum install google-noto-sans-cjk-fonts
sudo yum install google-noto-serif-cjk-fonts

# 或使用 EPEL 仓库
sudo yum install epel-release
sudo yum install wqy-microhei-fonts
```

#### macOS 系统
macOS 已经内置了中文字体（PingFang、Heiti），无需额外安装。

#### Windows 系统
Windows 已经内置了中文字体（微软雅黑、黑体、宋体），无需额外安装。

---

### 方案 2：使用字体工具模块（零配置）

系统已内置 `font_utils.py` 模块，提供：

#### 自动特性
- ✅ 自动检测系统可用字体
- ✅ 多层回退机制（Noto → 文泉驿 → Windows/macOS 字体）
- ✅ 启动时自动配置
- ✅ 运行时零配置

#### 使用方法

**方法 1：在 execute_python 工具中自动使用**
```python
# 工具会自动注入字体支持，无需手动配置
import matplotlib.pyplot as plt

fig, ax = plt.subplots()
ax.plot([1, 2, 3], [1, 4, 9])
ax.set_title('中文标题')  # ✅ 自动支持中文
plt.savefig('chart.png')
```

**方法 2：在独立脚本中使用**
```python
from app.utils.font_utils import configure_chinese_font
import matplotlib.pyplot as plt

# 配置字体（只需调用一次）
configure_chinese_font()

# 现在可以正常显示中文
fig, ax = plt.subplots()
ax.set_title('中文标题测试 - 污染物浓度变化')
ax.set_xlabel('时间')
ax.set_ylabel('浓度 (μg/m³)')
plt.savefig('chart.png')
```

**方法 3：在应用启动时全局配置**
```python
# 在 main.py 或 app 初始化时
from app.utils.font_utils import configure_chinese_font

configure_chinese_font()  # 全局配置，所有后续代码都支持中文
```

---

### 方案 3：运行检测脚本

系统提供了字体检测脚本，可以检查系统字体状态：

```bash
# 运行检测
cd /home/xckj/suyuan/backend
python scripts/check_font_support.py
```

**输出示例：**
```
============================================================
  中文字体支持检测
============================================================

⚙️  正在配置中文字体...
✅ 字体配置成功！

============================================================
  可用的中文字体
============================================================
  ✅ Noto Sans CJK JP
  ✅ Noto Serif CJK JP
  ❌ Noto Sans CJK SC
  ❌ WenQuanYi Micro Hei

============================================================
  当前字体配置
============================================================
  当前字体: Noto Sans CJK JP
  Unicode minus: False
  Math fontset: dejavusans

============================================================
  中文渲染测试
============================================================
✅ 中文渲染测试通过！

📊 测试图表已生成并验证

============================================================
  检测结果总结
============================================================
✅ 系统字体配置正常，可以正常显示中文和数字！
```

---

## 故障排除

### 问题 1：仍然显示方框

**原因**：系统没有安装中文字体

**解决**：
```bash
# Ubuntu/Debian
sudo apt install fonts-noto-cjk

# 验证安装
python scripts/check_font_support.py
```

### 问题 2：数字显示方框

**原因**：某些字体不支持数字字符

**解决**：使用 `Noto Sans CJK` 字体（支持中文和数字）

### 问题 3：LaTeX 数学符号显示异常

**原因**：中文字体不支持 LaTeX 数学公式

**解决**：系统已自动配置 `mathtext.fontset = 'dejavusans'`，数学符号使用 DejaVu 字体渲染

---

## 最佳实践

### 1. 开发环境配置
```bash
# 一键安装所有依赖（包括字体）
cd /home/xckj/suyuan/backend
sudo apt install fonts-noto-cjk  # 只需运行一次
```

### 2. 代码规范
```python
# ✅ 推荐：使用 font_utils（自动配置）
from app.utils.font_utils import configure_chinese_font
configure_chinese_font()

# ❌ 不推荐：硬编码字体路径
plt.rcParams['font.sans-serif'] = ['SimHei']  # 可能不存在
```

### 3. CI/CD 集成
```yaml
# .github/workflows/test.yml
- name: Install Chinese fonts
  run: sudo apt install fonts-noto-cjk

- name: Run tests
  run: python scripts/check_font_support.py
```

---

## 技术细节

### 字体回退链
```
Noto Sans CJK SC (简体中文，推荐)
    ↓ (不可用)
Noto Sans CJK TC (繁体中文)
    ↓ (不可用)
Noto Sans CJK JP (日文，也支持简体)
    ↓ (不可用)
WenQuanYi Micro Hei (文泉驿)
    ↓ (不可用)
Microsoft YaHei (Windows)
    ↓ (不可用)
DejaVu Sans (最后回退，不支持中文)
```

### 自动检测机制
1. 扫描 `/usr/share/fonts` 系统目录
2. 检查用户字体目录 `~/.local/share/fonts`
3. 尝试注册字体文件
4. 运行测试验证中文渲染

---

## 常见问题 FAQ

**Q: 为什么不直接在代码中硬编码字体路径？**
A: 不同系统的字体路径不同，硬编码会导致跨平台问题。使用 `font_utils` 可以自动适配。

**Q: Noto Sans CJK 和文泉驿哪个更好？**
A: Noto Sans CJK 是 Google 开发的，覆盖更全面（支持简繁日韩），推荐使用。

**Q: 如何查看系统已安装的字体？**
A: 运行 `fc-list :lang=zh` 命令

**Q: 字体文件很大（>100MB），会不会影响性能？**
A: 不会。matplotlib 只在首次使用时加载字体，后续使用缓存。

---

## 更新日志

- **2026-05-14**: 创建字体工具模块 `font_utils.py`
- **2026-05-14**: 添加字体检测脚本 `check_font_support.py`
- **2026-05-14**: 修复 `execute_python_tool.py` 字体回退机制

---

## 相关文件

- `app/utils/font_utils.py` - 字体管理工具
- `app/tools/utility/execute_python_tool.py` - Python 执行工具（已集成字体支持）
- `scripts/check_font_support.py` - 字体检测脚本
- `docs/FONT_SETUP_GUIDE.md` - 本文档
