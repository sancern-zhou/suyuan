# 许昌上风向企业筛选数据

场景一站点偏差告警使用有效排污许可证和企业排放清单的并集筛选上风向候选企业。

## 排放清单注册

源文件保存在项目数据目录：

`backend/backend_data_registry/source_files/xuchang/01-清单数据_汇总表（企业）_补充高德POI坐标.xlsx`

在 `backend/` 目录和项目 Python 3.11 Conda 环境中执行：

```bash
python -m scripts.register_xuchang_emission_inventory \
  'backend/backend_data_registry/source_files/xuchang/01-清单数据_汇总表（企业）_补充高德POI坐标.xlsx' \
  --inventory-period unknown
```

收到具有明确年份或统计周期的新清单时，用实际周期替换 `unknown` 并重新执行。注册使用稳定
`data_id`，运行中的 worker 需要重启后加载新资产。

注册过程会读取全部工作表，过滤说明行和空白尾行，按统一社会信用代码聚合企业的工艺排放量。
只有“已匹配”且具有有效经纬度的企业进入空间候选资产。高德 GCJ-02 坐标在注册时统一转换为
EPSG:4326；区县、乡镇、村庄等待核验结果不参与公里级空间筛选。

## 结果边界

清单排放量用于 PM2.5、O3 和 NOX 候选企业的相对优先级排序。它是清单周期估算量，不代表
告警时段的实际排放，输出不得解释为贡献率或责任认定。许可证继续提供有效状态、许可污染物和
监管信息；同一信用代码的两源记录在候选查询阶段合并并保留来源标识。
