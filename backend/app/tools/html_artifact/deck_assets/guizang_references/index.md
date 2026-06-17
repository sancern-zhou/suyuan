# Guizang HTML Deck Reference Index

调用 `create_html_artifact` 且 `display_mode=presentation`、`layout_system=guizang` 时，先读取本文件，再按 `presentation_style` 渐进读取对应资源。不要从零自写 deck CSS；`html_content` 应基于所选模板和 layouts 骨架改写。

## Magazine

`presentation_style=magazine` 时依次读取：

1. `../guizang_assets/template.html`
2. `layouts.md`
3. `themes.md`
4. `checklist.md`

## Swiss

`presentation_style=swiss` 时依次读取：

1. `../guizang_assets/template-swiss.html`
2. `layouts-swiss.md`
3. `themes-swiss.md`
4. `checklist.md`
5. `swiss-layout-lock.md`

## Optional References

- 需要图片提示词时读取 `image-prompts.md`。
- 需要截图/首屏构图检查时读取 `screenshot-framing.md`。
- 需要瑞士风地图组件时读取 `swiss-map-component.md`。
