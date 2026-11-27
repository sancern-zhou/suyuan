# 年度目标/168排名回补（00重要基础数据.zip）

《00重要基础数据.zip》官方年度统计表入库：4 张年度/排名表 + 语义层注册。
数据为**官方定版统计口径**（非明细聚合），与月报（CountyMonthReport 等）互补。

## 表与 Cube

| 表 | Cube | 覆盖 | 内容 |
|---|---|---|---|
| XuchangCityYearTarget | 同名 | 许昌市 2015-2026 | 年度目标 vs 实际（国家网口径；目标值全库唯一；SO2/NO2/CO/O3 年均 2015-2020） |
| XuchangCountyYearTarget | 同名 | 10 县市区 2020-2025 | 年度目标 vs 实际 + 完成判定（剔沙尘考核定版） |
| HenanCityYearTarget | 同名 | 18 地市 2021-2025 | 省考核目标完成情况 + 5-9 月臭氧超标天（2022-2023） |
| Rank168CityMonthly | 同名 | 168 城 2026-01~07 | 部发布综合指数/PM2.5 及全国排名（当月+累计） |

## 口径要点（Agent 路由已同步）

- **年度考核一律用年度表**，勿从明细或月报累计自算；月度过程分析用 CountyMonth/ProvinceMonth。
- 县级重污染天：年度表为剔沙尘考核口径；CountyMonthReport 月报 2023 年未剔沙尘，
  系统性差 3~4 天（2023-03 沙尘）。两口径都保留，按问题类型路由。
- 01 表"APP数据"两列（省发布平台口径）未入库，只取国家网"实际值"列。
- 省考核表与市口径偶有 1 μg 差（2022 许昌 PM2.5 省 47/市 46，Remark 注明），两表并存。
- 18 城表 2025 行未定稿（实际值疑沿用 2024 草稿），Remark 已注明。
- Rank168 仅用于全国排名；许昌浓度绝对值以本地口径为准。

## 已知数据质量裁决（导入前校验结论）

- 建安区/示范区 2023 重污染天：05表=12（与官方考核 doc、Sheet1 一致）取 12，
  剔沙尘表=13 仅在 Remark 注明。
- 长葛市 2023 PM2.5 年度考核 49 vs 月报累计 46.99：官方修订差，原值并存。
- 2015-2020 市级 PM2.5：01 表考核值 vs CityYearPm25Avg.Actual（实时未审核）差 1~5 μg，
  后者是平台口径未动。

## 源文件

`/root/suyuan/data/00重要基础数据_extracted/`（data/ 不入 git）：
01_xuchang_city_year.xlsx（原件）、03_henan_city_year.xlsx（.et 转换）、
04_county_heavy_days_sandfree.xlsx（.et 转换）、05_xuchang_county_year.xlsx（.xls 转换）、
06_rank168_monthly.xlsx（原件）。zip 原件在 `/root/suyuan/data/00重要基础数据.zip`。

.et/.xls 转换（宿主机）:

```bash
HOME=/tmp soffice --headless --convert-to xlsx --outdir /root/suyuan/data/00重要基础数据_extracted <源文件>
```

## 流程

```bash
P=/opt/miniconda3/envs/backend_py311/bin/python
cd projects/xuchang/data-ops/backfill_year_target
$P parse_year_targets.py                 # 解析 -> /tmp/year_target_csv/*.csv（含两表冲突仲裁）
$P validate_year_targets.py              # 与库内月报/年度表交叉校验
$P import_year_targets.py                # 幂等建表+upsert
# 新增/改动 Cube 后:
docker restart suyan-xuchang-cube        # schema 目录新增 .js 不热加载
$P ../../../../projects/xuchang/data-ops/semantic/validate_registry.py
$P ../../../../projects/xuchang/data-ops/semantic/gen_semantic_artifacts.py --check
```

后续年度更新：官方发布新年度表后，把新 xlsx 放入 extracted 目录（保持文件名），
重跑 parse（必要时按新 sheet 布局调整列映射）→ validate → import。
