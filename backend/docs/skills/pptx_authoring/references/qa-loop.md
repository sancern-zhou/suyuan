# QA 闭环协议（qa-loop）

生成 → 渲染验收 → 修复 → 重验收。**没有经过本闭环的 PPTX 不算交付物。**

## 1. 验收调用

```json
validate_pptx({
  "path": "<上次 artifact_path 返回的 file_path>",
  "expected_fonts": ["Noto Sans CJK SC"]
})
```

## 2. 结果解读

读返回的 `data`：

- `gate.status`：`passed`（可交付）/ `needs_revision`（按表修复后重验）/ `qa_failed`
  （渲染或验证流程本身异常——先修渲染环境/文件损坏，不得跳过验收交付）。
- `gate.blocking`：true 表示存在 high 级问题，必须修复。
- `structured_issues[]`：每项含 `type/severity/slide/message/evidence/artifacts`；
  `artifacts.page_png` 是该页渲染图路径，`artifacts.montage` 是全 deck 总览。
- `metrics`：design_score / visual_score（≥78 good，65–77 acceptable，<65 必须返工）。

## 3. 修复对照表（issue type → 动作）

| type | 动作 |
|---|---|
| high_text_density / moderate_text_density | 拆页；要点改卡片（每卡 ≤2 行）；删次要文字（红线 ≤620 字/20 行） |
| text_only_slide | 加指标卡/图表/形状结构；业务图走 create_business_chart 嵌入 |
| weak_title_hierarchy | 页标题提到 28–32pt |
| tiny_text | 最小字号提到 ≥10pt |
| low_typographic_contrast | 拉开层级：标题与正文差 ≥8pt |
| shape_out_of_bounds | 钳制坐标到画布+边距内（code-recipes §9） |
| rendered_low_margin | 内容区内缩（左右 ≥0.6in/上下 ≥0.45in） |
| rendered_nearly_blank / rendered_sparse_or_blank | 检查文本/图片是否真的写入（常见：save 前漏加 shape、图片路径空） |
| rendered_visual_overcrowding / rendered_dense_composition | 减元素：一页一主信息；表格转图表；删装饰形状 |
| rendered_corner_cluster | 坐标系算错（全挤在原点附近）或字体未生效：用栅格辅助重排 |
| rendered_content_overflow | 文本框太小/word_wrap 未开：加高文本框或删字 |
| repeated_layout_pattern | 相邻页交替版式（图表+洞察 → 卡片 → 表格） |
| expected_font_missing | 中文未设 eastasia 字体（code-recipes §2）；expected_fonts 参数写对 |
| validation_error / rendered_visual_qa_unavailable | 渲染环境异常：检查 pptx 是否损坏（能否本地 Presentation() 打开重存），仍失败则降级为简化版式重生成 |

## 4. 迭代纪律

- 每轮：修改生成代码 → 重新 execute_python 生成（覆盖同一 artifact_path 文件）→ 重新 validate_pptx。
- 最多 **3 轮**。3 轮后仍有非阻断（low/medium）问题且 design/visual score ≥78 可交付并在汇报中说明；
  仍有 blocking 或 score <65 → 换更简单的版式组合（指标条+图表双栏是兜底结构）重来，不要在复杂版式上无限修补。
- 修复必须针对 `evidence`（坐标/字符数/字号）精确调整，禁止盲目整体缩放。
- 每轮先看 `montage` 总览定位最差页，再按页读 `page_png` 复核，比逐 issue 盲改快。

## 5. 视觉自评（确定性 gate 通过后必须执行）

工具返回 `visual_review.worst_pages`（渲染分数最差 3 页）与 `montage_path`。**确定性检查只能拦"坏了"，拦不住"丑了"**——gate 通过后必须亲自看图：

1. `read_file(path=<montage_path>, as_multimodal_attachment=true)` 挂载总览，定位观感最差页
2. 对 `worst_pages`（及总览中发现的疑似页）逐页 `read_file(path=<png_path>, as_multimodal_attachment=true)` 挂载
3. 每页按以下标准给 pass/fail（判定基线：用户会不会接受这一页）：

| 维度 | 检查点 |
|---|---|
| 版面密度 | 留白 ≥20%；无贴边、无拥挤堆叠 |
| 对齐 | 同排元素等高、左缘对齐；无错位悬浮元素 |
| 字号层级 | 标题明显突出；正文观感 ≥10pt；层级差清晰 |
| 配色 | 文字对比度足够；语义色一致（优良轻度中重）；无刺眼撞色 |
| 图表可读 | 轴标签/图例/数据标注清晰可辨；线条不糊 |
| 中文渲染 | 无豆腐块、无字体漂移（宋体混入 = eastasia 未设，回 code-recipes §2 修） |

4. fail 项：能定位到代码的（字号/坐标/配色）直接修；观感类问题（拥挤/层级弱）按修复对照表的对应动作处理
5. 修复后重生成 + 重新 validate_pptx + 重新自评，与确定性循环合计仍 ≤3 轮
6. **交付标准：确定性 gate passed 且视觉自评无 fail 页**；仍有观感瑕疵必须显式说明并给理由
