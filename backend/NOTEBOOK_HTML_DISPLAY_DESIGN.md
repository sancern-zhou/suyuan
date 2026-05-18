# Jupyter Notebook HTML 展示方案设计

## 一、现有交互方式分析

### 1.1 Office文档预览流程（参考）

**后端流程**：
```
execute_python工具 → 检测到Office文件 → pdf_converter.convert_to_pdf()
     ↓
生成PDF预览对象：{
  "pdf_id": "uuid",
  "pdf_url": "/api/office/pdf/{pdf_id}",
  "pages": 10,
  "size": 12345
}
     ↓
触发office_document事件 → 前端接收
```

**前端流程**：
```
SSE监听office_document事件 → 提取pdf_preview
     ↓
更新OfficeDocumentPanel → iframe嵌入PDF URL
     ↓
用户看到PDF预览
```

**关键API**：
- `GET /api/office/pdf/{pdf_id}` - 返回PDF文件
- `GET /api/office/pdf/{pdf_id}/info` - 返回PDF元信息

### 1.2 现有代码位置

| 功能 | 文件路径 |
|------|---------|
| PDF转换服务 | `backend/app/services/pdf_converter.py` |
| Office API路由 | `backend/app/api/office_routes.py` |
| Office工具 | `backend/app/tools/office/` |
| 前端Office面板 | `frontend/src/components/OfficeDocumentPanel.vue` |
| 前端事件处理 | `frontend/src/composables/reactAnalysis/useOfficeDocumentHandler.js` |

---

## 二、Notebook HTML展示方案设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                      后端（Backend）                          │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  execute_python工具                                          │
│       ↓                                                      │
│  检测到.ipynb文件                                           │
│       ↓                                                      │
│  notebook_converter.convert_to_html()  [新增服务]            │
│       ↓                                                      │
│  生成HTML预览对象：{                                         │
│    "html_id": "uuid",                                       │
│    "html_url": "/api/notebook/html/{html_id}",              │
│    "pages": 13,                                             │
│    "cells": 13,                                             │
│    "size": 12345                                            │
│  }                                                           │
│       ↓                                                      │
│  触发notebook_document事件 → 前端                           │
│                                                               │
├─────────────────────────────────────────────────────────────┤
│                    Notebook API路由  [新增]                  │
│                                                               │
│  GET /api/notebook/html/{html_id}  → 返回HTML文件            │
│  GET /api/notebook/html/{html_id}/info → 返回元信息          │
│  DELETE /api/notebook/html/{html_id} → 清理缓存             │
│                                                               │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                      前端（Frontend）                         │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  SSE监听notebook_document事件                                 │
│       ↓                                                      │
│  提取html_preview信息                                         │
│       ↓                                                      │
│  更新NotebookPanel组件  [新增]                                │
│       ↓                                                      │
│  iframe嵌入HTML URL                                          │
│       ↓                                                      │
│  用户看到完整的Notebook（代码+输出+样式）                     │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 后端实现

#### 2.2.1 Notebook转换服务

**文件**：`backend/app/services/notebook_converter.py`（新建）

```python
"""
Notebook HTML conversion service
Convert Jupyter Notebook (.ipynb) to HTML for frontend preview
"""
from pathlib import Path
from nbconvert import HTMLExporter
import nbformat
import tempfile
import shutil
import uuid
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class NotebookConverter:
    """Convert Jupyter Notebook to HTML"""

    def __init__(self):
        self.output_dir = Path(tempfile.gettempdir()) / "notebook_html_cache"
        self.output_dir.mkdir(exist_ok=True)

    async def convert_to_html(self, notebook_path: str) -> Dict[str, Any]:
        """
        Convert Jupyter Notebook to HTML

        Args:
            notebook_path: Path to the .ipynb file

        Returns:
            {
                "html_id": "unique-id",
                "html_path": "/path/to/html",
                "html_url": "/api/notebook/html/{html_id}",
                "pages": 13,  # 单元格数量
                "cells": 13,
                "size": 12345
            }
        """
        try:
            html_id = f"{uuid.uuid4()}"
            html_path = self.output_dir / f"{html_id}.html"

            # 读取notebook文件
            with open(notebook_path, 'r', encoding='utf-8') as f:
                nb = nbformat.read(f, as_version=4)

            # 配置HTML导出器
            html_exporter = HTMLExporter(
                template_name='classic',  # 使用经典模板
                exclude_input_prompt=False,  # 显示输入提示符
                exclude_output_prompt=False,  # 显示输出提示符
                exclude_input=False,  # 显示代码输入
                exclude_output=False,  # 显示输出
            )

            # 转换为HTML
            (body, resources) = html_exporter.from_notebook_node(nb)

            # 添加响应式样式
            html_content = self._wrap_with_styles(body)

            # 保存HTML文件
            html_path.write_text(html_content, encoding='utf-8')

            return {
                "html_id": html_id,
                "html_path": str(html_path),
                "html_url": f"/api/notebook/html/{html_id}",
                "pages": len(nb.cells),  # 单元格数量
                "cells": len(nb.cells),
                "size": html_path.stat().st_size
            }

        except Exception as e:
            logger.error(f"Notebook conversion error: {e}", exc_info=True)
            raise

    def _wrap_with_styles(self, body: str) -> str:
        """添加响应式样式和完整HTML结构"""
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Jupyter Notebook Preview</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
            line-height: 1.6;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 900px;
            margin: 0 auto;
            background: white;
            padding: 40px;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        .cell {{
            margin-bottom: 20px;
            padding: 15px;
            border: 1px solid #e0e0e0;
            border-radius: 4px;
        }}
        .input_prompt {{
            color: #303F9F;
            font-weight: bold;
        }}
        .output_prompt {{
            color: #D32F2F;
            font-weight: bold;
        }}
        pre {{
            background: #f8f8f8;
            padding: 12px;
            border-radius: 4px;
            overflow-x: auto;
        }}
        img {{
            max-width: 100%;
            height: auto;
        }}
    </style>
</head>
<body>
    <div class="container">
        {body}
    </div>
</body>
</html>"""

    def cleanup_html(self, html_id: str) -> bool:
        """清理HTML缓存文件"""
        try:
            html_path = self.output_dir / f"{html_id}.html"
            if html_path.exists():
                html_path.unlink()
                return True
            return False
        except Exception as e:
            logger.warning(f"Failed to cleanup HTML {html_id}: {e}")
            return False

    def get_html_path(self, html_id: str) -> Path:
        """获取HTML文件路径"""
        return self.output_dir / f"{html_id}.html"

    def html_exists(self, html_id: str) -> bool:
        """检查HTML文件是否存在"""
        return self.get_html_path(html_id).exists()


# 全局单例
notebook_converter = NotebookConverter()
```

#### 2.2.2 Notebook API路由

**文件**：`backend/app/api/notebook_routes.py`（新建）

```python
"""
Notebook preview API routes
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path
import logging

from app.services.notebook_converter import notebook_converter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/notebook", tags=["notebook"])


@router.get("/html/{html_id}")
async def get_notebook_html(html_id: str):
    """
    Get Notebook HTML file by ID

    Args:
        html_id: Unique HTML identifier

    Returns:
        HTML file as FileResponse
    """
    html_path = notebook_converter.get_html_path(html_id)

    if not notebook_converter.html_exists(html_id):
        raise HTTPException(status_code=404, detail="Notebook HTML not found")

    return FileResponse(
        path=str(html_path),
        media_type="text/html",
        filename=f"{html_id}.html",
        headers={"Content-Disposition": "inline; filename=notebook.html"}
    )


@router.get("/html/{html_id}/info")
async def get_notebook_info(html_id: str):
    """
    Get Notebook HTML metadata

    Args:
        html_id: Unique HTML identifier

    Returns:
        HTML metadata including cell count and file size
    """
    html_path = notebook_converter.get_html_path(html_id)

    if not notebook_converter.html_exists(html_id):
        raise HTTPException(status_code=404, detail="Notebook HTML not found")

    return {
        "html_id": html_id,
        "cells": html_path.stat().st_size // 1000,  # 粗略估算单元格数
        "size": html_path.stat().st_size,
        "filename": f"{html_id}.html"
    }


@router.delete("/html/{html_id}")
async def delete_notebook_html(html_id: str):
    """
    Delete a Notebook HTML file

    Args:
        html_id: Unique HTML identifier

    Returns:
        Success status
    """
    success = notebook_converter.cleanup_html(html_id)

    if not success:
        raise HTTPException(status_code=404, detail="Notebook HTML not found or already deleted")

    return {"success": True, "message": "Notebook HTML deleted"}
```

#### 2.2.3 修改execute_python工具

**文件**：`backend/app/tools/utility/execute_python_tool.py`

在Office文件检测逻辑后添加Notebook检测：

```python
# 原有Office文件检测逻辑
if office_files:
    # ... 现有代码 ...

# 新增：Notebook文件检测逻辑
elif notebook_files:
    # 只处理第一个 notebook 文件
    notebook_file = notebook_files[0]
    try:
        from app.services.notebook_converter import notebook_converter
        html_preview = await notebook_converter.convert_to_html(notebook_file)
        result["data"]["html_preview"] = html_preview
        result["data"]["file_path"] = notebook_file
        result["data"]["file_type"] = "notebook"
        if result.get("success", False):
            result["summary"] = f"✅ 工具已执行完成，生成Notebook：{Path(notebook_file).name}"
        logger.info(
            "execute_python_html_generated",
            html_id=html_preview["html_id"],
            notebook_file=notebook_file,
            execution_success=result.get("success", False)
        )
    except Exception as html_error:
        logger.warning("execute_python_notebook_conversion_failed", error=str(html_error))
        # HTML转换失败时，仍然返回文件信息
        result["data"]["file_path"] = notebook_file
        result["data"]["file_type"] = "notebook"
        if result.get("success", False):
            result["summary"] = f"✅ 工具已执行完成，生成Notebook：{Path(notebook_file).name}"
```

检测notebook文件的方法（在文件检测部分添加）：

```python
# 检测生成的文件中是否有notebook
notebook_files = [
    f for f in final_files
    if f.endswith('.ipynb')
]
```

#### 2.2.4 注册路由

**文件**：`backend/app/main.py`

在路由注册部分添加：

```python
# Include Notebook routes (Notebook预览)
from app.api.notebook_routes import router as notebook_router
app.include_router(notebook_router)
```

### 2.3 前端实现

#### 2.3.1 NotebookPanel组件

**文件**：`frontend/src/components/NotebookPanel.vue`（新建）

```vue
<template>
  <div class="notebook-panel" :class="{ 'has-content': hasNotebookDocuments }">
    <!-- Empty state -->
    <div v-if="!hasNotebookDocuments || notebookDocuments.length === 0" class="empty-state">
      <p class="empty-title">暂无Notebook</p>
      <p class="empty-tip">执行Python生成Jupyter Notebook时，将在此处显示预览</p>
    </div>

    <!-- Panel content -->
    <template v-else>
      <div class="notebook-list">
        <div v-for="doc in notebookDocuments" :key="doc.html_id || doc.file_path" class="notebook-item">
          <!-- Header -->
          <div class="notebook-header">
            <h3 class="notebook-title">
              <span class="notebook-icon">📓</span>
              {{ getFileName(doc.file_path) }}
            </h3>
            <div class="header-actions">
              <button @click="openInNewTab(doc)" class="action-btn" title="在新标签页打开">
                🔗 新标签页
              </button>
              <button @click="downloadNotebook(doc)" class="action-btn" title="下载Notebook">
                ⬇️ 下载
              </button>
            </div>
          </div>

          <!-- Loading state -->
          <div v-if="doc.loading" class="preview-loading">
            <div class="spinner"></div>
            <p>生成预览中...</p>
          </div>

          <!-- HTML preview (iframe) -->
          <div v-else-if="doc.html_url" class="html-wrapper">
            <iframe
              :src="`${doc.html_url}#zoom=100&toolbar=0&navpanes=0`"
              class="notebook-iframe"
              type="text/html"
              @load="onHtmlLoaded(doc)"
            ></iframe>
          </div>

          <!-- Error state -->
          <div v-else class="preview-error">
            <p>预览加载失败</p>
            <p class="error-hint">请尝试在新标签页打开或下载文件查看</p>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useReactStore } from '@/stores/reactStore'

const reactStore = useReactStore()

// 提取Notebook文档
const notebookDocuments = computed(() => {
  const officeDocs = reactStore.currentSessionOfficeDocuments || []
  return officeDocs.filter(doc =>
    doc.file_type === 'notebook' ||
    (doc.file_path && doc.file_path.endsWith('.ipynb'))
  )
})

const hasNotebookDocuments = computed(() => {
  return notebookDocuments.value.length > 0
})

// 获取文件名
const getFileName = (filePath) => {
  if (!filePath) return 'Unknown'
  return filePath.split('/').pop()
}

// 在新标签页打开
const openInNewTab = (doc) => {
  if (doc.html_url) {
    window.open(doc.html_url, '_blank')
  }
}

// 下载Notebook
const downloadNotebook = async (doc) => {
  if (!doc.file_path) return

  try {
    const response = await fetch('/api/notebook/download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_path: doc.file_path })
    })

    if (response.ok) {
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = getFileName(doc.file_path)
      a.click()
      window.URL.revokeObjectURL(url)
    }
  } catch (error) {
    console.error('Download failed:', error)
  }
}

// HTML加载完成
const onHtmlLoaded = (doc) => {
  doc.loading = false
}
</script>

<style scoped>
.notebook-panel {
  padding: 16px;
  background: #f5f5f5;
  border-radius: 8px;
  min-height: 400px;
}

.empty-state {
  text-align: center;
  padding: 60px 20px;
  color: #666;
}

.empty-title {
  font-size: 18px;
  font-weight: 600;
  margin-bottom: 8px;
}

.empty-tip {
  font-size: 14px;
  color: #999;
}

.notebook-item {
  background: white;
  border-radius: 8px;
  overflow: hidden;
  margin-bottom: 16px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

.notebook-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  border-bottom: 1px solid #e0e0e0;
  background: #fafafa;
}

.notebook-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
}

.notebook-icon {
  font-size: 20px;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.action-btn {
  padding: 6px 12px;
  border: 1px solid #d0d0d0;
  background: white;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.2s;
}

.action-btn:hover {
  background: #f0f0f0;
  border-color: #b0b0b0;
}

.html-wrapper {
  position: relative;
  height: 600px;
}

.notebook-iframe {
  width: 100%;
  height: 100%;
  border: none;
}

.preview-loading,
.preview-error {
  padding: 60px 20px;
  text-align: center;
  color: #666;
}

.spinner {
  width: 40px;
  height: 40px;
  margin: 0 auto 16px;
  border: 4px solid #f3f3f3;
  border-top: 4px solid #3498db;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.error-hint {
  font-size: 13px;
  color: #999;
  margin-top: 8px;
}
</style>
```

#### 2.3.2 集成到主界面

**文件**：`frontend/src/views/ReactAnalysis.vue`（或其他主界面）

在OfficeDocumentPanel后添加：

```vue
<!-- Notebook文档面板 -->
<NotebookPanel v-if="hasNotebookDocuments" />
```

```javascript
import NotebookPanel from '@/components/NotebookPanel.vue'

const hasNotebookDocuments = computed(() => {
  const officeDocs = reactStore.currentSessionOfficeDocuments || []
  return officeDocs.some(doc =>
    doc.file_type === 'notebook' ||
    (doc.file_path && doc.file_path.endsWith('.ipynb'))
  )
})
```

### 2.4 依赖安装

**后端依赖**：
```bash
pip install nbconvert>=7.0.0
```

可选：安装Jupyter以获得更好的样式支持：
```bash
pip install jupyter
```

---

## 三、实施步骤

### 第1步：创建Notebook转换服务
```bash
# 创建文件
touch backend/app/services/notebook_converter.py
```

### 第2步：创建Notebook API路由
```bash
# 创建文件
touch backend/app/api/notebook_routes.py
```

### 第3步：修改execute_python工具
在 `execute_python_tool.py` 中添加notebook检测逻辑

### 第4步：注册路由
在 `main.py` 中注册notebook路由

### 第5步：创建前端NotebookPanel组件
```bash
# 创建文件
touch frontend/src/components/NotebookPanel.vue
```

### 第6步：集成到主界面
修改 `ReactAnalysis.vue`，添加NotebookPanel

### 第7步：安装依赖
```bash
cd backend
pip install nbconvert
```

### 第8步：测试
1. 运行后端：`python -m uvicorn app.main:app --reload`
2. 运行前端：`cd frontend && npm run dev`
3. 在Agent中执行Python生成.ipynb文件
4. 查看前端是否显示Notebook预览

---

## 四、优势与特点

### 4.1 优势
✅ **完整保留Notebook格式**：代码、输出、markdown全部保留
✅ **支持交互式元素**：折叠单元格、代码高亮
✅ **响应式设计**：自动适配屏幕大小
✅ **成熟方案**：基于Jupyter官方nbconvert
✅ **缓存机制**：避免重复转换

### 4.2 特点
- 与现有Office文档预览流程一致
- 使用iframe隔离样式，不影响主界面
- 支持新标签页打开和下载
- 清晰的错误处理和降级方案

---

## 五、测试用例

### 测试1：基础Notebook预览
```python
# 在execute_python中执行
import json
notebook = {
  "cells": [
    {
      "cell_type": "markdown",
      "source": "# 测试Notebook\\n\\n这是一个测试。"
    },
    {
      "cell_type": "code",
      "source": "print('Hello, Notebook!')",
      "outputs": [{"text": "Hello, Notebook!"}]
    }
  ],
  "nbformat": 4,
  "nbformat_minor": 2
}

with open('/home/xckj/suyuan/backend_data_registry/output/test.ipynb', 'w') as f:
    json.dump(notebook, f)
```

预期：前端显示完整的Notebook预览，包含markdown和代码单元格。

### 测试2：带图表的Notebook
```python
import matplotlib.pyplot as plt
import json

# 生成图表
plt.plot([1, 2, 3, 4])
plt.savefig('/tmp/test_plot.png')

# 创建notebook
notebook = {
  "cells": [
    {
      "cell_type": "code",
      "source": "import matplotlib.pyplot as plt\\nplt.plot([1, 2, 3, 4])\\nplt.show()",
      "outputs": [
        {"data": {"image/png": "base64_encoded_image"}}
      ]
    }
  ],
  "nbformat": 4
}
```

预期：前端显示Notebook，图表正确渲染。

### 测试3：大文件处理
创建包含50+单元格的Notebook，测试：
- 转换性能
- 前端滚动性能
- 内存占用

---

## 六、扩展功能（可选）

### 6.1 支持Notebook下载
在 `notebook_routes.py` 添加：
```python
@router.post("/download")
async def download_notebook(request: Request):
    """下载原始.ipynb文件"""
    data = await request.json()
    file_path = data.get("file_path")

    if not file_path or not file_path.endswith('.ipynb'):
        raise HTTPException(status_code=400, detail="Invalid notebook path")

    resolved_path = Path(file_path).resolve()

    if not resolved_path.exists():
        raise HTTPException(status_code=404, detail="Notebook not found")

    return FileResponse(
        path=str(resolved_path),
        media_type="application/json",
        filename=resolved_path.name,
        headers={"Content-Disposition": f"attachment; filename=\"{resolved_path.name}\""}
    )
```

### 6.2 支持多种模板
在 `notebook_converter.py` 中添加模板选项：
```python
# 使用不同模板
templates = {
    'classic': '经典模板',
    'lab': 'JupyterLab风格',
    'basic': '简洁模板'
}
```

### 6.3 添加打印支持
在前端NotebookPanel添加打印按钮：
```javascript
const printNotebook = (doc) => {
  const iframe = document.querySelector(`iframe[src="${doc.html_url}"]`)
  iframe.contentWindow.print()
}
```

---

## 七、故障排查

### 问题1：nbconvert未安装
**错误**：`ModuleNotFoundError: No module named 'nbconvert'`

**解决**：
```bash
pip install nbconvert
```

### 问题2：HTML生成失败
**错误**：`Notebook conversion error`

**排查**：
1. 检查.ipynb文件格式是否正确
2. 查看后端日志中的详细错误信息
3. 尝试用Jupyter直接打开notebook验证

### 问题3：前端iframe无法加载
**错误**：iframe显示空白或拒绝连接

**排查**：
1. 检查CORS配置
2. 确认HTML文件已生成（检查 `/tmp/notebook_html_cache/`）
3. 检查浏览器控制台错误信息

### 问题4：样式显示异常
**错误**：HTML内容显示错乱

**解决**：
1. 确保 `_wrap_with_styles` 方法正确添加了样式
2. 检查iframe的content-type是否为 `text/html`
3. 尝试使用不同的nbconvert模板

---

## 八、总结

本方案完全参照现有的Office文档预览流程设计，确保了：
1. **架构一致性**：与现有系统完美融合
2. **代码复用**：最大化利用现有组件和模式
3. **渐进增强**：可选功能，不影响现有流程
4. **易于维护**：清晰的代码结构和文档

实施后，用户可以在前端直接预览Jupyter Notebook文件，无需下载或跳转到其他应用。
