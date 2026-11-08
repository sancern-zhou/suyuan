# 广东站点运行日报配置

共享实现先提交main，本目录及广东站点接口实现属于project/guangdong。在该分支先合并main，再维护本项目配置。不要将本机.env或运行registry提交到Git。

`config.json`采用已实测的省控监测站点小时接口，同时查询国控和省控，保留原始实况（data_type=0）和质量标记。国控独立发布源未接入，日报有明确说明。

## 名录口径（2026-11-06 核对，以业务方官方清单为准）

- **国控 125 站**：业务方提供的官方国控名录，编码与名称逐条核对一致。其中麻章区环保局 1054A、环境监控中心 1071A、市政府 1073A 平台 72 小时实测无数据，保留在名录内（不会产生离线事件，会以候选站出现在报告末尾）。
- **省控 163 站 = 官方名录 160 站 + 3 个交接站**：160 站名录由业务方提供，编码与名称逐条核对一致。另加十四五期间由国控转省控的南城元岭 4634A、东城主山 4639A、莞城梨川 1086A（日报首页固定说明已载明该交接事项）。其中狮山港 1387A、武江白芒 1436A 平台实测无数据。
- 合计 288 站，国控与省控编码无交集。`roster_provenance` 与 `roster_classification` 记录来源、计数及无数据站清单，供审计追溯。
- **报数口径**：报告的国控/省控站点数反映**监控名录范围**，而非当次实际取到数据的站数。一个未上传数据的站在业务上仍在监控范围内。

名录与运行库的镜像关系：`MonitorStore.seed()` 每次采集都会以配置名录为准同步 `stations` 表，配置中已移除的编码会从表中删除，不再累积为“无记录候选站点”。

名单维护要点：旧名单曾混用另一套编码体系（如深圳福田莲花写作4554A，平台实为1431A），这类编码在接口上永远取不到数据。核对时不要用单小时探测判定编码失效——当前离线站点在该小时同样无数据；应回看至少72小时，或与 monitor.sqlite3 的历史 cells 记录交叉验证。

## 准备与试跑

使用实际conda环境运行：

```
python /path/to/guangdong-worktree/projects/guangdong/station_operation_monitor/deploy.py --deployment-root /path/to/deployment --env-file backend/.env --preview
```

相对env路径以部署项目根为准。工具和Fetcher从部署工作树的backend启动，使用env显式配置的同一DATA_REGISTRY_DIR。本机main部署为/home/xckj/suyuan-main，不能从测试工作树启动正式web/worker。

准备命令保存配置、完整任务定义和实际数据样稿到registry的station_operation_monitor_prepared，不写正式config.json，不创建或启用定时任务。

## 启用

先完成测试和样稿审核。暂停对应部署worker后执行同一命令加`--apply`（不必加--preview），再按该部署的启动流程成对确认web/worker。apply只创建不存在的正式配置和任务，不覆盖运行中用户修改；变更现有配置须显式处理。

- 采集：定时任务gd_station_operation_hourly_collect按cron `30 * * * *`每小时30分采集上一个整点小时（10:30跳过，日报工作流自带同窗口取数）。采集只入库不生成报告；取数失败即任务失败并显性报错，不静默视为正常。
- 日报：workflow定时任务gd_station_operation_daily，每天北京时间10:30，汇总过去24小时并生成Word/PDF。
- 同一站点的延续事件与当前事件在存在未观察盲区时合并为一条累计事件，时长按报告起止跨度计算（`observed_missing_hours`保留实际核实的缺失小时数）。
- Agent固定工具：station_operation_daily；确定性结果与Word由该工具生成并声明统一资源，Agent直接交付，不自行重算或臆测。
- 首次正式采集需运行共享CLI collect建立历史快照；没有快照的过去离线无法完整还原。
- 当前没有启用对外广播。

省控无法回补的确认通过unrecoverable_confirmations提供，每项须含code、覆盖缺失区间的start/end、reason、evidence、confirmed_by、confirmed_at。不具备核实证据时保持待回补，实际补齐后已回补优先于旧确认。

不要为日报部署另一个backend工作树或复用其他项目registry。当前共享工作树存在其他未提交修改时，重启会同时载入这些修改，需在启用前明确处理。
