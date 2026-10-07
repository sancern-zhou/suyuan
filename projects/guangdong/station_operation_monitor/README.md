# 广东站点运行日报配置

共享实现先提交main，本目录及广东站点接口实现属于project/guangdong。在该分支先合并main，再维护本项目配置。不要将本机.env或运行registry提交到Git。

`config.json`采用已实测的省控监测站点小时接口，同时查询国控和省控，保留原始实况（data_type=0）和质量标记。国控独立发布源未接入，日报有明确说明。站点名单为265个候选编码，并非确认在运总数；未取得数据者不会自动成为离线站点。人工核实后可在部署registry中的配置设置confirmed和active。

## 准备与试跑

使用实际conda环境运行：

```
python /path/to/guangdong-worktree/projects/guangdong/station_operation_monitor/deploy.py --deployment-root /path/to/deployment --env-file backend/.env --preview
```

相对env路径以部署项目根为准。工具和Fetcher从部署工作树的backend启动，使用env显式配置的同一DATA_REGISTRY_DIR。本机main部署为/home/xckj/suyuan-main，不能从测试工作树启动正式web/worker。

准备命令保存配置、完整任务定义和实际数据样稿到registry的station_operation_monitor_prepared，不写正式config.json，不创建或启用定时任务。

## 启用

先完成测试和样稿审核。暂停对应部署worker后执行同一命令加`--apply`（不必加--preview），再按该部署的启动流程成对确认web/worker。apply只创建不存在的正式配置和任务，不覆盖运行中用户修改；变更现有配置须显式处理。

- 采集：FetcherScheduler每小时25分执行station_operation_monitor。
- 日报：custom定时任务gd_station_operation_daily，每天北京时间10:30。
- Agent固定工具：station_operation_daily；确定性结果与Word由该工具生成并声明统一资源，Agent直接交付，不自行重算或臆测。
- 首次正式采集需运行共享CLI collect建立历史快照；没有快照的过去离线无法完整还原。
- 当前没有启用对外广播。

省控无法回补的确认通过unrecoverable_confirmations提供，每项须含code、覆盖缺失区间的start/end、reason、evidence、confirmed_by、confirmed_at。不具备核实证据时保持待回补，实际补齐后已回补优先于旧确认。

不要为日报部署另一个backend工作树或复用其他项目registry。当前共享工作树存在其他未提交修改时，重启会同时载入这些修改，需在启用前明确处理。
