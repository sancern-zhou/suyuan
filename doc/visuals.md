# Visuals 规范（UDF v2.0 扩展）

本文件说明分析工具输出的 `visuals` payload 规范，以及前端如何消费后端生成的静态图（SVG/PNG）和交互数据（JSON payload）。

1. visuals 顶级结构（示例）

```json
{
  "id": "visual_001",
  "type": "stacked_time",            // 图表类型（stacked_time/ternary/heatmap/network/...)
  "schema": "chart_config_v1",       // schema 版本
  "payload": {
    "data": [...],                   // 绘图用的数组 records（时间序列请使用 ISO8601 timestamp）
    "x": "timestamp",                // x 字段名（可为 null）
    "series": ["OM","NO3","SO4"],    // 要绘制的字段
    "size": null,                    // 可选：点大小字段
    "color": null                    // 可选：点颜色字段
  },
  "meta": {
    "generator": "calculate_reconstruction",
    "version": "0.1",
    "rendered_files": { "svg": "path/to.svg", "png": "path/to.png" } // 渲染后由渲染服务填充
  }
}
```

2. 渲染策略（后端渲染服务）
- 分离：分析工具负责输出标准化 `visuals`，渲染由后端渲染服务（或独立任务）完成。  
- 输出文件：优先生成矢量文件（SVG/PDF），同时生成兼容前端的位图 `PNG`（便于手机/旧浏览器）。渲染函数返回文件路径字典，例如 `{"svg": "...", "png": "..."}`。  
- 缓存：渲染服务应基于 `visuals.payload` 的 hash + generator_version 做缓存，避免重复渲染。  

3. 前端消费方式
- 若 `meta.rendered_files` 存在，前端优先加载 `png`（跨浏览器兼容）或 `svg`（支持缩放与后期编辑）。  
- 若无预渲染文件，前端可使用 `visuals.payload` 及 `schema` 在 ECharts/Plotly 中即时绘制交互图。  
- 建议前端在展示缩略图时使用 `png`，在用户需要下载或放大时尝试加载 `svg`。

4. Metadata 必填项（建议）
- `generator`、`version`、`source_data_hash`、`params`（如 oc_to_om、negative_handling）、`render_time`、`random_seed`（若存在随机性）。  

5. 静态图导出规范
- SVG：可编辑、保留文本，不转路径。  
- PNG：默认 400 DPI（出版级 400-600），文件名包含 `visual_id`、`generator_version`、`dpi`、`hash`。  

6. 兼容与示例
- 示例调用：分析工具返回 `visuals`，渲染服务接收 `visuals.payload` 并写入 `meta.rendered_files`；前端拉取该 metadata 并展示图片或回退为交互绘图。









