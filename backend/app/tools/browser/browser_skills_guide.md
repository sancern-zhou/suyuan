# 浏览器工具技能指导（v3.3）

> **MANDATORY**: 复杂浏览任务或浏览器调用失败后必读；简单打开网页、截图、提取页面文本等任务可直接调用工具
>
> **v3.3更新**: 修复execute_js工具使用方法，移除错误的arguments用法

## 🚀 核心原则（MANDATORY）

```
1. 陌生页面必先 snapshot
2. 优先使用 ref 而非 selector
3. 顺序执行，禁止并发
4. Wait失败立即snapshot，不要重试相同选择器
5. Element blocked立即用execute_js，不要尝试其他选择器
```

**绝对禁止**：
```
❌ .btn, .el-button, .ant-btn, button, input, div
❌ 并发浏览器操作
❌ execute_js中使用 arguments[0]  ⚠️ 新增禁止项
```

---

## ⚡ 激进模式（常用网站）⭐ 推荐

**对于常用标准网站，直接操作，无需snapshot**，节省时间和token：

### 搜索引擎

**必应 (Bing)** ⭐ 推荐搜索引擎：
```python
# 直接搜索（无验证码，推荐）
from urllib.parse import quote
search_url = f"https://www.bing.com/search?q={quote('广东旭诚科技有限公司')}"
browser(action="navigate", url=search_url)
browser(action="wait", load_state="domcontentloaded", timeout=5000)
```


### 搜索结果操作

**必应 (Bing) 搜索结果提取** ⭐ 推荐：
```python
# 提取搜索结果
browser(action="execute_js", code="""
    () => {
        const results = [];
        document.querySelectorAll('li.b_algo').forEach(item => {
            const link = item.querySelector('a');
            if (link) {
                const href = link.getAttribute('href');
                const title = link.textContent.trim();
                if (href && title) {
                    results.push({title: title, url: href});
                }
            }
        });
        return results;
    }
""")
```

**方法1：直接DOM提取** ⭐⭐⭐⭐⭐

```python
# 执行JavaScript提取mu属性
browser(action="execute_js", code="""
    () => {
        const results = [];
        document.querySelectorAll('div.result[mu]').forEach(container => {
            const mu = container.getAttribute('mu');
            const h3 = container.querySelector('h3');
            if (mu && h3) {
                results.push({
                    title: h3.textContent.trim(),
                    url: mu
                });
            }
        });
        return results;
    }
""")
```



**示例：提取特定关键词的搜索结果**
```python
# 执行JavaScript提取并过滤
browser(action="execute_js", code="""
    () => {
        const keyword = '旭诚科技';  // 目标关键词
        const results = [];

        document.querySelectorAll('div.result[mu]').forEach(container => {
            const mu = container.getAttribute('mu');
            const h3 = container.querySelector('h3');
            const title = h3 ? h3.textContent.trim() : '';

            // 按关键词过滤
            if (mu && title.includes(keyword)) {
                results.push({
                    title: title,
                    url: mu
                });
            }
        });

        return results[0] || null;  // 返回第一个匹配，或null
    }
""")
```

**方法2：混合方法（先snapshot了解结构，再DOM提取）** ⭐⭐⭐⭐

```python
# 第1步：获取页面结构了解（可选）
browser(action="snapshot", format="ai", compact=True)

# 第2步：直接DOM提取（推荐）
browser(action="execute_js", code="""
    () => {
        // 根据snapshot了解的结构，精准提取
        const containers = document.querySelectorAll('div.result');
        const results = [];

        containers.forEach(container => {
            const mu = container.getAttribute('mu');
            if (mu) {
                results.push(mu);
            }
        });

        return results;
    }
""")
```

**方法3：refs参数（高级用法）** ⭐⭐⭐

```python
# 第1步：获取snapshot
snapshot_result = browser(action="snapshot", format="ai", compact=True)

# 第2步：从snapshot中提取refs
refs = snapshot_result['data']['refs']

# 第3步：使用refs参数（注意：需要传递refs参数）
browser(action="execute_js", code="""
    (refs) => {
        for (const [refId, refData] of Object.entries(refs)) {
            if (refData.html_attrs && refData.html_attrs.mu) {
                const mu = refData.html_attrs.mu;
                if (mu.includes('目标关键词')) {
                    return mu;
                }
            }
        }
        return null;
    }
""", refs=refs)  # ⚠️ 必须传递refs参数
```

**⚠️ 禁止的错误用法**：
```python
# ❌ 错误：使用arguments[0]（会导致"arguments is not defined"错误）
browser(action="execute_js", code="""
    () => {
        const refs = arguments[0];  # ❌ 错误！
        // ...
    }
""")

# ❌ 错误：期望refs自动注入
browser(action="execute_js", code="""
    () => {
        // 期望refs变量自动可用  # ❌ 错误！refs不会自动注入
        for (const [refId, refData] of Object.entries(refs)) {
            // ...
        }
    }
""")
```

**最佳实践总结**：
1. **优先使用方法1**（直接DOM提取）- 最简单、最可靠
2. 只在需要详细元素信息时使用方法2（混合方法）
3. 方法3（refs参数）仅用于高级场景

### 常用网站

**必应 (Bing)** - 搜索引擎 ⭐ 推荐：
```python
from urllib.parse import quote
search_url = f"https://www.bing.com/search?q={quote('搜索内容')}"
browser(action="navigate", url=search_url)
browser(action="wait", load_state="domcontentloaded", timeout=5000)
# 提取搜索结果使用 execute_js (参见上方)
```

**知乎** (www.zhihu.com)：
```python
browser(action="navigate", url="https://www.zhihu.com")
browser(action="wait", selector="input[placeholder*='搜索']", timeout=5000)
browser(action="act", selector="input[placeholder*='搜索']", text="搜索内容")
```

---

## 🛠️ Execute JS 使用规范（v3.3新增）


### 基本语法

**格式1：包含箭头函数**（推荐，更清晰）：
```python
browser(action="execute_js", code="""
    () => {
        // 直接访问DOM
        return document.title;
    }
""")
```

**格式2：不包含箭头函数**（兼容旧版本）：
```python
browser(action="execute_js", code="""
    document.title
""")
```

**带参数版本**：
```python
# 传递自定义参数
browser(action="execute_js", code="""
    (param) => {
        return param * 2;
    }
""", refs=21)
```

**refs参数版本**：
```python
# 从snapshot获取refs后使用
snapshot = browser(action="snapshot", format="ai", compact=True)
refs = snapshot['data']['refs']

browser(action="execute_js", code="""
    (refs) => {
        return Object.keys(refs).length;
    }
""", refs=refs)
```

**重要**：execute_js v2.2会自动检测代码格式，两种格式都支持！

### 常见任务示例

**1. 点击被遮挡的元素**：
```python
browser(action="execute_js", code="""
    () => {
        const btn = document.querySelector('button:has-text("确定")');
        if (btn) btn.click();
        return !!btn;
    }
""")
```

**2. 移除遮挡对话框**：
```python
browser(action="execute_js", code="""
    () => {
        document.querySelectorAll('.el-dialog').forEach(d => d.remove());
        return 'removed';
    }
""")
```

**3. 提取页面数据**：
```python
browser(action="execute_js", code="""
    () => {
        const data = [];
        document.querySelectorAll('.item').forEach(item => {
            data.push({
                title: item.querySelector('.title')?.textContent,
                price: item.querySelector('.price')?.textContent
            });
        });
        return data;
    }
""")
```

**4. 滚动到页面底部**：
```python
browser(action="execute_js", code="""
    () => {
        window.scrollTo(0, document.body.scrollHeight);
        return 'scrolled';
    }
""")
```

### 重要约束

1. **必须使用箭头函数或函数声明**
   ```python
   # ✅ 正确
   code="() => { return document.title; }"
   code="function() { return document.title; }"

   # ❌ 错误（裸代码）
   code="return document.title;"
   ```

2. **禁止使用arguments对象**
   ```python
   # ❌ 错误
   code="() => { const args = arguments[0]; }"

   # ✅ 正确（使用参数）
   code="(param) => { return param; }", refs=my_data
   ```

3. **返回值必须是JSON可序列化**
   ```python
   # ✅ 正确
   code="() => { return {title: 'test', count: 5}; }"

   # ❌ 错误
   code="() => { return document.body; }"  # DOM对象无法序列化
   ```

---

## 📋 保守模式（陌生页面）

**标准流程**（适用于陌生/定制页面）：
```python
browser(action="start")
browser(action="navigate", url="...")
browser(action="snapshot", format="ai", compact=True)  # 获取refs
browser(action="act", ref="e1", text="用户名")
browser(action="act", ref="e2", text="密码")
browser(action="act", ref="e3", click=True)
browser(action="wait", text_gone="登录中", timeout=10000)
browser(action="stop")
```

**必须snapshot场景**：
- 陌生内网系统
- 定制业务系统
- 动态SPA页面（React/Vue/Angular）
- 中文企业内部系统
- wait失败后

---

## 🎯 决策树

```
访问常用网站？
├─ 是 → 在激进模式列表中？→ 直接操作（无需snapshot）
│        └─ 否 → 尝试直接wait，失败则snapshot
└─ 否（陌生页面）→ 必须先snapshot
```

---

## 🔍 选择器优先级

```
激进模式（常用网站）：
1. 标准属性：#kw, input[name='login']        ⭐⭐⭐⭐⭐
2. 文本选择器：button:has-text("登录")      ⭐⭐⭐⭐⭐
3. execute_js直接DOM查询                    ⭐⭐⭐⭐⭐  (v3.3新增)

保守模式（陌生页面）：
1. ref="e1"（从snapshot获取）              ⭐⭐⭐⭐⭐
2. button:has-text("登录")                  ⭐⭐⭐⭐⭐
3. [placeholder*="用户"]                    ⭐⭐⭐⭐

❌ 禁止：.btn, .el-button, .ant-btn, button, input, div
❌ 禁止：execute_js中使用arguments[0]       ⚠️ v3.3新增
```

---

## ⚡ 错误恢复（MANDATORY）

| 错误 | 解决方法 |
|------|----------|
| **Wait Timeout** | ⚠️ 激进模式→改用selector<br>⚠️ 保守模式→立即snapshot |
| **Element blocked** | ⚠️ 立即 `execute_js` 绕过 |
| **arguments is not defined** | ⚠️ 使用箭头函数参数或直接DOM查询<br>⚠️ 不要使用arguments[0] |
| **Thread error** | 禁止并发操作 |
| **No context** | 先 `action="start"` |

### Execute JS 错误恢复

```
错误：arguments is not defined
原因：使用了 arguments[0] 获取参数
解决：使用函数参数 (param) => { ... } 并传递参数

错误：Cannot read property 'xxx' of null
原因：选择器未找到元素
解决：先snapshot确认元素存在，或使用 try-catch
```

---

## 🔧 核心操作

### 生命周期
- `start/stop/status`: 浏览器管理

### 导航
- `navigate`: 打开URL
- `open/tabs/focus/close`: 标签页管理

### 获取信息
- `snapshot`: 页面结构（陌生页面必用）⭐
- `screenshot`: 截图
- `extract`: 提取数据

### 交互
- `act`: 元素操作
  - `selector="..."`: 激进模式使用
  - `ref="e1"`: 保守模式使用（从snapshot获取）
  - `click=True`: 点击
  - `text="..."`: 输入
  - `press="Enter"`: 按键
- `execute_js`: JS代码执行 ⭐ v3.3增强
  - **无参数**: `code="() => { ... }"`
  - **带参数**: `code="(param) => { ... }", refs=value`
  - **refs参数**: `code="(refs) => { ... }", refs=refs_dict`

### 等待
- `wait`: 条件等待
  - `selector="..."`: 元素可见
  - `text="..."`: 文本出现
  - `load_state="domcontentloaded"`: 加载状态
  - `timeout=5000`: 超时时间（激进模式用5000，保守用20000）

---
