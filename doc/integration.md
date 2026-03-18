# 渲染服务与前端集成说明

本文档说明如何把后端分析 `visuals` 与渲染服务集成到前端应用。

1) 后端流程
- 分析工具（如 `calculate_reconstruction`）输出标准化 UDF v2.0 响应，包含 `visuals` 字段。  
- 渲染服务接收 `visuals`（或 `visuals.payload`），执行模板渲染（Matplotlib 等），保存文件到静态存储（本地 `mapout/`、对象存储或 CDN），并把路径写回 `visuals.meta.rendered_files`。  
- 渲染可异步：渲染 API 返回 `task_id`，前端轮询任务状态或接收 webhook 后获取 `rendered_files`。

2) 前端行为
- 优先加载 `visuals.meta.rendered_files.png`（兼容性最佳），若需要放大下载则使用 `svg`。  
- 若 `rendered_files` 不存在，前端可直接用 `visuals.payload` 在 ECharts/Plotly 中渲染交互图。  

3) 安全与性能
- 对渲染任务进行限速，限制 DPI/图片尺寸；渲染放入工作队列并限制并发。  
- 对上传/生成的静态文件做权限/过期策略（例如 7 天 CDN 缓存，长期报告归档）。  

4) 接口示例（伪 API）
- POST /render -> body: { "visual": { ... } } -> 返回 { "task_id": "..." }  
- GET /render/{task_id} -> 返回 { "status": "done", "files": {"svg":"...","png":"..."} }









