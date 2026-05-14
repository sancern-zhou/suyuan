# 字体问题快速参考卡片

## 🚨 问题症状
- ❌ 中文字符显示为方框 `▯▯▯`
- ❌ 数字无法显示
- ❌ 图表标题、标签乱码

---

## ✅ 快速解决方案

### 1️⃣ 系统级修复（一劳永逸）
```bash
# Ubuntu/Debian
sudo apt update && sudo apt install fonts-noto-cjk

# CentOS/RHEL
sudo yum install google-noto-sans-cjk-fonts
```

### 2️⃣ 代码级修复（零配置）
```python
# ✅ 方案A：使用自动工具（推荐）
from app.utils.font_utils import configure_chinese_font
configure_chinese_font()

# ✅ 方案B：使用 execute_python 工具（自动支持）
# 工具会自动注入字体支持，无需手动配置
```

---

## 🔍 检测工具

### 运行字体检测
```bash
cd /home/xckj/suyuan/backend
python scripts/check_font_support.py
```

### 预期输出
```
✅ 系统字体配置正常，可以正常显示中文和数字！
```

---

## 🧪 测试验证

### 运行单元测试
```bash
pytest tests/test_font_utils.py -v
```

### 手动测试
```python
import matplotlib.pyplot as plt
from app.utils.font_utils import configure_chinese_font

configure_chinese_font()

fig, ax = plt.subplots()
ax.set_title('中文标题测试 - 污染物浓度变化')
ax.set_xlabel('时间 (月)')
ax.set_ylabel('浓度 (μg/m³)')
plt.savefig('test.png')
```

---

## 📊 字体回退链

系统会按以下顺序尝试字体：

```
Noto Sans CJK SC (简体中文) ⭐
    ↓
Noto Sans CJK TC (繁体中文)
    ↓
Noto Sans CJK JP (日文，也支持简体) ⭐
    ↓
WenQuanYi Micro Hei (文泉驿)
    ↓
Microsoft YaHei (Windows)
    ↓
DejaVu Sans (最后回退)
```

---

## 🛠️ 故障排除

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| 仍然显示方框 | 系统无中文字体 | `sudo apt install fonts-noto-cjk` |
| 数字显示方框 | 字体不支持数字 | 使用 Noto Sans CJK |
| LaTeX 符号异常 | 中文字体不支持数学公式 | 已自动配置 `mathtext.fontset` |
| 跨平台兼容性 | 硬编码字体路径 | 使用 `font_utils.py` 工具 |

---

## 📁 相关文件

| 文件 | 说明 |
|------|------|
| `app/utils/font_utils.py` | 字体管理工具（核心） |
| `scripts/check_font_support.py` | 字体检测脚本 |
| `tests/test_font_utils.py` | 单元测试 |
| `docs/FONT_SETUP_GUIDE.md` | 完整指南 |
| `app/tools/utility/execute_python_tool.py` | Python执行工具（已集成） |

---

## 🎯 最佳实践

### ✅ 推荐做法
```python
# 1. 使用工具自动配置
from app.utils.font_utils import configure_chinese_font
configure_chinese_font()

# 2. 使用 execute_python 工具（自动支持）
# 工具会自动注入字体支持，无需手动配置

# 3. 在应用启动时全局配置
# main.py
from app.utils.font_utils import configure_chinese_font
configure_chinese_font()
```

### ❌ 避免做法
```python
# 1. 不要硬编码字体路径
plt.rcParams['font.sans-serif'] = ['SimHei']  # ❌ 可能不存在

# 2. 不要使用不支持中文的字体
plt.rcParams['font.sans-serif'] = ['DejaVu Sans']  # ❌ 不支持中文

# 3. 不要手动注册字体文件
# ❌ 容易出错，使用 font_utils.py 代替
```

---

## 📝 验证清单

在部署前，确保：

- [ ] 运行 `python scripts/check_font_support.py` 通过
- [ ] 运行 `pytest tests/test_font_utils.py` 全部通过
- [ ] 手动测试生成包含中文的图表
- [ ] 确认数字和科学符号正常显示
- [ ] 跨平台测试（Linux/Windows/macOS）

---

## 🚀 CI/CD 集成

```yaml
# .github/workflows/test.yml
- name: Install Chinese fonts
  run: sudo apt install fonts-noto-cjk

- name: Check font support
  run: python scripts/check_font_support.py

- name: Run font tests
  run: pytest tests/test_font_utils.py -v
```

---

## 💡 技术要点

### 自动检测机制
1. 扫描系统字体目录
2. 检查字体文件是否存在
3. 尝试注册字体文件
4. 运行测试验证渲染

### 多层回退策略
1. 字体文件注册（最高优先级）
2. 系统字体查找
3. 默认回退字体（DejaVu Sans）

### 跨平台支持
- **Linux**: Noto Sans CJK, 文泉驿
- **Windows**: 微软雅黑, 黑体
- **macOS**: 苹方, 黑体

---

## 📞 获取帮助

如果问题仍未解决：

1. 查看完整指南：`docs/FONT_SETUP_GUIDE.md`
2. 运行检测脚本：`python scripts/check_font_support.py`
3. 查看单元测试：`tests/test_font_utils.py`
4. 检查日志输出

---

**最后更新**: 2026-05-14
**维护者**: Claude Code
**版本**: 1.0.0
