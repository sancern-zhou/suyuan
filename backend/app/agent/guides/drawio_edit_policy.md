# Draw.io Edit Policy

本文件约束现有 draw.io 画板的编辑策略。

## 编辑优先级

1. 用户明确选中元素时，优先编辑 `board_context.selected_cells`。
2. 用户使用“这个”“这里”“当前选中”“刚才那个模块”等指代时，必须绑定到选中元素。
3. 用户没有选中元素时，根据文本、id、上下游连线和位置推断目标；不确定时先说明需要确认。
4. 除非用户明确要求全局重构，否则只修改与请求直接相关的 cell。

## operation 选择

1. 新建画板：`operation="create"`。
2. 修改已有节点文本：`operation="edit"` + `update_label`。
3. 修改已有节点样式：`operation="edit"` + `update_style`。
4. 修改已有节点位置或尺寸：`operation="edit"` + `move_resize`。
5. 添加连线：`operation="edit"` + `connect`。
6. 删除节点及相关连线：`operation="edit"` + `delete_with_edges`。
7. 添加完整新节点：`operation="edit"` + `add`。
8. 复杂替换整个 mxCell：`operation="edit"` + `update`。
9. 多个相关修改应放在同一次 `operations` 中，避免半成品状态。

## 选中目标

1. 如果用户选中了画布元素，优先使用 `target="selected"`，并把 `board_context.selected_cells` 原样传给工具。
2. `target="selected"` 会解析为 `selected_cells` 的第一个 cell id。
3. 如果用户同时选中多个元素但请求没有明确对象，先编辑第一个选中元素；需要批量修改时，为每个 cell 生成独立 operation。
4. 没有选中元素时，必须显式传 `cell_id`、`source_cell_id`、`target_cell_id`。

## 结构化局部编辑规则

1. `update_label` 使用 `label` 或 `value`，不需要 `new_xml`。
2. `update_style` 使用 `style_patch` 修改局部样式键，例如 `{"fillColor": "#f8cecc", "strokeColor": "#b85450"}`；也可用 `style` 完整替换样式。
3. `move_resize` 使用 `geometry`，可只传需要修改的 `x`、`y`、`width`、`height`。
4. `connect` 使用 `cell_id` 作为新连线 id，使用 `source_cell_id` 和 `target_cell_id` 指定端点；端点可使用 `"selected"`。
5. `delete_with_edges` 会删除目标 cell，并级联删除其子节点和 source/target 指向它的连线。
6. 只有新增完整节点或复杂替换时才使用 `add`/`update` 的 `new_xml`。

## 局部编辑规则

1. `update` 的 `new_xml` 必须包含完整的新 mxCell，且 id 必须等于 `cell_id`。
2. `add` 的 `new_xml` 必须包含完整的新 mxCell，且 id 必须等于 `cell_id`。
3. `delete` 不需要 `new_xml`，但优先使用 `delete_with_edges` 表达删除节点及相关连线。
4. 添加新节点时，应同时添加必要连线。
5. 调整布局时，只移动相关区域，保留其他区域坐标。

## 失败恢复

1. 如果工具返回 XML 无效、id 冲突、source/target 不存在等错误，先修正 operations 后重试。
2. 不要把失败的 XML 直接展示给用户。
3. 如果缺少 `board_context.current_xml`，不能假装已有画板；应新建或向用户说明需要当前画板状态。

## 上下文使用

1. `board_context.current_xml` 是权威全量状态。
2. `board_context.selected_cells` 是当前用户选中对象的局部上下文。
3. 大图编辑时，优先使用 selected cells 和相关上下游节点做局部 patch。
