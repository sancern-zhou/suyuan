# 河南城市历史气象

许昌项目启用共享 `city_weather_history_fetcher`，点位在 `project.yaml` 的
`backend.weather_history.points` 配置。覆盖河南17个地级市及济源，采用现有城市
气象站定位作为代表点，许昌保留原有坐标34.036、113.852。实际查询键仍按既有
0.25度坐标对齐；这不代表上游实际使用ERA5模型或该分辨率。

数据来源为 Open-Meteo Best Match。保存逐小时边界层高度、温湿度、风、辐射等
字段，不能标注为纯ERA5、站点实测或全市平均。

## 采集和查询

- Worker每5分钟检查持久任务队列；每天创建一次最近7个UTC日的补缺任务。
- 首次运行补最近90个UTC日，截止昨天UTC。每点按30日分块，最多每轮处理60块。
- 边界层高度缺失、非有限值、负值或旧来源未验证时需要补采；0米是有效值。
- 相同任务去重，分块保存进度，重启后续跑；部分失败任务间隔至少1小时重试。
- `get_weather_data`先读库；不超过3个点且少于7日跨度的请求允许20秒在线补采。
  更大范围或超时会入队，单次自动补采上限为100个点、366个UTC日。
- 当天、未来和近期仍缺失的数据使用`get_weather_forecast`，保留来源区别。
- 返回`metadata.history_backfill.jobs`提供任务id、状态、已处理块数和总块数；
  再次查询可读取补采结果。对比使用`metadata.comparison_coverage`中的共同有效小时。
- 任务库位于`DATA_REGISTRY_DIR/weather_history/<project>/jobs.sqlite3`，web和worker
  必须共享同一持久目录；采用SQLite事务和进程锁，不适用于多机器独立文件系统。

## 运维命令

从后端运行目录，在对应项目环境已加载的`backend_py311`环境中执行：

```bash
python -m app.services.weather_history_cli collect
python -m app.services.weather_history_cli run --max-chunks 60
python -m app.services.weather_history_cli backfill --start-date 2026-01-01 --end-date 2026-03-31 --cities 许昌市 郑州市
python -m app.services.weather_history_cli status --job-id <id>
```

日期参数表示UTC日期。`collect`和`backfill`只入队，常驻worker负责执行；`run`
可人工推进任务，与常驻worker互斥。`partial`表示仍有缺失或请求失败，应核查
失败块和真实字段覆盖，不得按写入行数宣称完整。
