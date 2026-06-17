# 浏览器工具使用指南（v3.9）

## 核心原则

1. 先观察，再操作：陌生页面先 `snapshot`，确认元素、frame、弹窗和当前页面状态。
2. 优先用 `snapshot` 返回的 `ref`，少用宽泛 selector；iframe 内元素使用 `fN:eM` 形式。
3. 浏览器操作必须顺序执行。不要并发点击、并发截图、并发等待。
4. 一次交互后不要只看 URL。必须确认页面状态是否变化：新 context、frame、overlay、DOM、history、network 都可能是结果。
5. 失败后先重新 `snapshot` 或截图，不要反复尝试同一个选择器。

## 交互后的状态模型

任何 click、submit、keypress、select、drag、JS 调用后，都不要预设结果一定是页面跳转。把结果理解为浏览器状态变化，并按下面顺序收敛：

1. **Browsing context**：是否出现新 tab、新窗口、新 iframe；frame URL 是否变化。
2. **Viewport layer**：是否出现 modal、dialog、drawer、popover、toast、遮罩或侧边面板。
3. **DOM state**：目标文本、表单、表格、展开区、按钮状态、loading 状态是否变化。
4. **History state**：主页面 URL、hash、query、title 是否变化。
5. **Network/load state**：请求是否完成，loading 是否消失，内容是否异步刷新。

判断交互是否成功时，优先等待“目标状态特征”，而不是等待“某一种导航形态”：

```python
browser(action="act", ref="目标控件ref", click=True)
browser(action="wait", text="目标状态中的稳定文本", timeout=10000)
browser(action="snapshot", format="ai", compact=True)
```

如果预期文本不确定，先检查结构性状态变化：

```python
browser(action="wait", selector="iframe, [role='dialog'], .modal, .drawer, .popover, .toast", timeout=5000)
browser(action="snapshot", format="ai", compact=True)
```

主 URL 没变不等于失败；新 tab 没出现也不等于失败。必须重新观察页面状态后再判断。

## iframe 规则

`snapshot` 默认包含 frame 信息，元素 ref 形如 `f0:e1`、`f1:e3`。

```python
# 直接操作 iframe 内元素
browser(action="act", ref="f1:e3", text="查询条件")

# 或显式指定 frame
browser(action="act", frame_index=1, selector="#search", click=True)
browser(action="execute_js", frame_index=1, code='document.title')
browser(action="screenshot", frame_index=1)
```

原则：

- 看到 iframe 页面时，不要只在主 frame 找元素。
- 点击后如果出现新 iframe，继续在新 iframe 中等待文本、截图或操作。
- frame URL 通常比主 URL 更能说明真实页面位置。

## 选择器策略

优先级：

1. `ref="fN:eM"`：从 snapshot 获取，最可靠。
2. 稳定唯一属性：`#id`、`[name=...]`、`[placeholder*=...]`。
3. 文本选择器：`button:has-text("提交")`、`a:has-text("打开")`。
4. 组合选择器：`tr:has-text("目标值") a[onclick]`。

避免：

- `.btn`、`.el-button`、`.ant-btn`、`button`、`input`、`div` 这类宽泛选择器。
- 多个元素匹配时直接点第一个，除非已经确认上下文。
- 表格中脱离行上下文点击重复控件，应优先绑定到目标行。

## 事件入口规则

页面控件不一定是普通链接。常见入口包括：

- 标准 `<button>`、`<a>`、`input[type=button]`。
- `href="javascript:void(0)"`。
- `onclick` 或框架绑定事件。
- 只有图标、title、aria-label，没有明显文本。
- 行内操作控件，需要结合所在行数据确认目标。

普通点击失败时，不要盲目换选择器。先检查元素的 `href`、`onclick`、role、title、aria-label、所在行文本，再决定是否用 `execute_js` 触发同一 DOM 事件。

`act` 参数语义必须区分清楚：

- `text`：只表示向可编辑控件填值，如 textbox、searchbox、combobox。
- `click=True`：用于 link、button、menu item、图标按钮、行内操作等动作控件。
- 元素的可见文字不是要填入的值；不要对 link/button 传 `text`。

```python
browser(action="execute_js", code="""
() => {
  const btn = [...document.querySelectorAll('tr')]
    .find(row => row.textContent.includes('目标值'))
    ?.querySelector('a[onclick], button, input[type=button]');
  btn?.click();
  return !!btn;
}
""")
```

## wait 使用

```python
# 固定等待 3 秒
browser(action="wait", timeout=3)

# 条件等待
browser(action="wait", text="加载完成", timeout=10000)
browser(action="wait", selector=".result", timeout=10000)
browser(action="wait", load_state="domcontentloaded", timeout=5000)
```

原则：

- 固定等待只用于短暂过渡。
- 条件等待失败后立刻 `snapshot`。
- 不要把等待主 URL 变化作为唯一成功条件。

## execute_js 规则

普通表达式可以直接写：

```python
browser(action="execute_js", code="document.title")
```

多语句代码可写成箭头函数并显式 `return`：

```python
browser(action="execute_js", code="""
() => {
  const title = document.title;
  return title;
}
""")
```

也支持常规脚本语句；需要结果时写 `return`：

```python
browser(action="execute_js", code="""
var title = document.title;
return title;
""")
```

禁止：

- `arguments[0]`。
- 返回 DOM 对象本身。返回字符串、数字、布尔值、数组或普通对象。

传参时使用函数参数：

```python
browser(action="execute_js", code="(refs) => Object.keys(refs).length", refs=refs)
```

## 错误恢复

| 现象 | 处理 |
| --- | --- |
| 找不到输入框或按钮 | `snapshot`，检查 frame 和 ref |
| 交互后 URL 不变 | 检查 context、frame、overlay、DOM、history、network |
| 点击被遮挡 | 用 `execute_js` 点击或移除遮罩 |
| 等待失败 | 立刻截图或 snapshot，不重复同一等待 |
| 选择器匹配多个 | 绑定目标行或改用 ref |
| execute_js 没有返回值 | 脚本语句需要显式 `return` |

## 最小工作流

```python
browser(action="start")
browser(action="navigate", url="...")
browser(action="snapshot", format="ai", compact=True)
browser(action="act", ref="f0:e1", click=True)
browser(action="wait", text="目标页面特征文本", timeout=10000)
browser(action="snapshot", format="ai", compact=True)
browser(action="screenshot", full_page=True)
```

完成任务前，用截图或 snapshot 证明页面状态，而不是只依赖工具调用成功。
