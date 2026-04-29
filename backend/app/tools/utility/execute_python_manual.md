# execute_python 工具指导手册

助手Agent和社交Agent在使用 `execute_python` 处理复杂计算、Excel、可视化或文件生成前，应先阅读本手册。简单的纯 Python 计算可直接调用。

## 适用场景

- 数据处理：`pandas`、`numpy`、`scipy`。
- Excel 读取、修改和生成：优先使用 `openpyxl`，读取分析可用 `pandas`。
- 图表生成：`matplotlib`，保存图片到 `backend_data_registry`。
- 文档生成：`python-docx`。
- 自定义统计：仅当专用查询/统计工具无法直接满足时使用。

## 文件路径

- 生成文件必须保存到项目可访问目录，优先使用 `/home/xckj/suyuan/backend_data_registry/`。
- 代码中打印保存路径，便于前端和后续工具定位。
- 工具会检测 `backend_data_registry` 中新增文件。

## matplotlib 中文和化学式

使用无界面后端：

```python
import matplotlib
matplotlib.use("Agg")
```

中文字体推荐直接指定字体文件：

```python
from matplotlib.font_manager import FontProperties
chinese_font = FontProperties(fname="/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc")
```

不要使用 Unicode 下标字符，例如 `O₃`、`PM₂.₅`、`NO₂`，部分字体会显示方框。使用 mathtext：

```python
ax.set_title(r"O$_3$浓度变化", fontproperties=chinese_font)
ax.set_ylabel(r"PM$_{2.5}$ ($\mu$g/m$^3$)", fontproperties=chinese_font)
```

常用写法：`O$_3$`、`NO$_2$`、`SO$_2$`、`PM$_{2.5}$`、`PM$_{10}$`。

## Excel 规则

- 修改现有 Excel 时优先用 `openpyxl`，避免 `pandas.to_excel()` 覆盖导致图表和格式丢失。
- 创建新文件可用 `pandas` 或 `openpyxl`。
- 公式优先保留为公式，不要硬编码可计算结果。
- 会商文件合并、图表保留等项目约定，以对应技能文档为准。

## 常见错误

- JSON/数据库读取的数值可能是字符串，计算前显式 `float()` 或 `int()`。
- 字典字段可能缺失，使用 `.get()` 并处理默认值。
- 使用变量前检查 `None`。
- 超时默认 30 秒，复杂任务应拆分或提高 `timeout`。

## 最小示例

```python
from docx import Document

out = "/home/xckj/suyuan/backend_data_registry/report.docx"
doc = Document()
doc.add_heading("报告", 0)
doc.save(out)
print(out)
```
