# Notebook分享功能测试指南

## 功能概述

实现了Notebook的双模式架构：
1. **正常阅读模式**：前端直接渲染Notebook JSON，无需生成HTML文件
2. **分享模式**：点击"分享"按钮生成独立的HTML文件，支持外网访问

## 配置说明

### 后端配置（.env）
```
FRONTEND_BASE_URL=http://219.135.180.51:56041
```

这个配置用于生成可访问的分享链接。

### 前端配置
无需额外配置，自动使用相对路径访问资源。

## 使用流程

### 1. 正常阅读Notebook

当Agent生成Notebook报告后，前端右侧面板会自动显示Notebook内容：

- **Markdown单元格**：使用MarkdownRenderer渲染
- **代码单元格**：显示代码和输出
- **图片输出**：自动从reports目录加载

**特点**：
- 无需后端生成HTML
- 加载速度快
- 支持交互式编辑

### 2. 分享Notebook

1. 在Notebook预览面板右上角，点击"📤 分享报告"按钮
2. 等待HTML生成（几秒钟）
3. 弹出对话框显示分享链接
4. 点击"复制"按钮复制链接
5. 将链接分享给他人

**分享链接格式**：
```
http://219.135.180.51:56041/reports/xxx_share.html
```

**特点**：
- 独立的HTML文件，可离线查看
- 图片使用base64嵌入，确保可移植性
- 响应式设计，支持移动端和桌面端

## 技术实现

### 后端工具

**工具名称**：`generate_shareable_notebook`

**功能**：
- 读取Notebook JSON文件
- 转换为HTML格式
- 嵌入base64图片
- 生成响应式HTML
- 保存到`frontend/public/reports/`目录

**API调用示例**：
```javascript
const response = await fetch('/api/tools/execute', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    tool: 'generate_shareable_notebook',
    parameters: {
      notebook_path: '/path/to/notebook.ipynb'
    }
  })
})
```

**返回结果**：
```json
{
  "success": true,
  "data": {
    "share_link": "http://219.135.180.51:56041/reports/xxx_share.html",
    "html_path": "/path/to/html"
  },
  "summary": "已生成分享链接: http://219.135.180.51:56041/reports/xxx_share.html"
}
```

### 前端组件

**NotebookRenderer.vue**：
- 直接渲染Notebook JSON
- 支持Markdown和代码单元格
- 显示图片输出
- 提供分享按钮

**OfficeDocumentPanel.vue**：
- 检测Notebook文档类型
- 异步加载Notebook JSON
- 集成NotebookRenderer组件

## 响应式设计

生成的HTML文件包含完整的响应式CSS：

- **移动端**（< 768px）：
  - 减小字体和间距
  - 单列布局
  - 触摸友好的按钮

- **桌面端**（≥ 768px）：
  - 更大的字体和间距
  - 多列布局（如需要）
  - 鼠标悬停效果

## 测试步骤

### 1. 测试正常阅读

```bash
# 1. 启动后端
cd backend
python -m uvicorn app.main:app --reload

# 2. 启动前端
cd frontend
npm run dev

# 3. 在浏览器中访问
# http://localhost:5174（或外网地址）
```

### 2. 测试分享功能

1. 使用Agent生成一个Notebook报告
2. 查看右侧面板是否正确显示Notebook内容
3. 点击"分享报告"按钮
4. 检查是否成功生成分享链接
5. 复制链接并在新标签页中打开
6. 验证链接在外网可访问
7. 测试移动端显示效果

### 3. 验证HTML文件

检查生成的HTML文件：
```bash
ls -lh frontend/public/reports/*_share.html
```

文件应该包含：
- 完整的HTML结构
- 响应式CSS样式
- Base64编码的图片
- 所有Notebook内容

## 常见问题

### Q: 分享链接无法访问？
A: 检查：
1. `FRONTEND_BASE_URL`配置是否正确
2. HTML文件是否成功生成
3. 前端服务器是否运行

### Q: 图片无法显示？
A: 正常阅读模式下，图片从reports目录加载；分享模式下，图片使用base64嵌入。

### Q: 移动端显示效果不佳？
A: 生成的HTML包含响应式CSS，应该自动适配移动端。如需调整，修改工具中的CSS样式。

## 后续优化

1. **性能优化**：
   - 添加HTML缓存机制
   - 支持增量更新

2. **功能增强**：
   - 支持自定义HTML模板
   - 添加水印功能
   - 支持密码保护

3. **用户体验**：
   - 添加生成进度提示
   - 支持批量分享
   - 添加分享历史记录
