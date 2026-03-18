# execute_js页面加载等待要求测试报告

## 测试目的

验证execute_js工具在使用mu属性提取时是否需要等待页面加载。

## 测试方法

测试5种不同的等待策略：

1. **立即提取** - 不等待，直接执行
2. **domcontentloaded** - 等待DOM加载完成
3. **networkidle** - 等待网络空闲
4. **networkidle + 2秒延迟** - 额外延迟
5. **等待特定元素** - 等待`div.result`元素出现

## 测试结果

### 测试1：立即提取
```
结果: 0 个结果
状态: ❌ 失败
```

### 测试2：domcontentloaded
```
结果: 8 个结果
示例: {'title': '广东旭诚科技有限公司', 'url': 'https://www.suncereltd.com/'}
状态: ✅ 成功
```

### 测试3：networkidle
```
结果: 8 个结果
示例: {'title': '广东旭诚科技有限公司', 'url': 'https://www.suncereltd.com/'}
状态: ✅ 成功
```

### 测试4：networkidle + 2秒延迟
```
结果: 8 个结果
示例: {'title': '广东旭诚科技有限公司', 'url': 'https://www.suncereltd.com/'}
状态: ✅ 成功
```

### 测试5：等待特定元素
```
结果: 8 个结果
示例: {'title': '广东旭诚科技有限公司', 'url': 'https://www.suncereltd.com/'}
状态: ✅ 成功
```

## 结论

### ⚠️ 关键发现

**必须等待页面加载才能成功提取mu属性！**

- 立即提取：**失败**（0个结果）
- 任何等待策略：**成功**（8个结果）

### 📋 推荐做法

**标准流程**：
```python
# 1. 导航到搜索结果页面
browser(action="navigate", url="https://www.baidu.com/s?wd=...")

# 2. 等待页面加载（必须！）
browser(action="wait", load_state="domcontentloaded", timeout=5000)

# 3. 执行JavaScript提取mu属性
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

### 🎯 最佳实践

1. **最小等待**：`load_state="domcontentloaded"` - DOM加载完成即可
2. **最可靠等待**：`load_state="networkidle"` - 网络完全空闲
3. **目标等待**：`selector="div.result"` - 等待特定元素出现

### 🔍 问题根因分析

之前的日志显示`result_type=null`，原因是：

1. LLM生成的代码是正确的
2. execute_js工具实现是正确的
3. **但代码在页面DOM加载完成之前就执行了**
4. 导致`querySelectorAll`找不到任何元素，返回空数组

### ✅ 解决方案

更新技能指南，明确要求：
- 执行execute_js前必须等待页面加载
- 推荐使用`wait(load_state="domcontentloaded")`
- 或者使用`wait(selector="div.result")`等待特定元素

## 测试环境

- 浏览器：Chromium (Playwright)
- 搜索关键词：广东旭诚科技有限公司
- 测试时间：2026-03-16
- 测试次数：5次（每种策略）

## 附件

- 详细测试结果：`backend/tests/browser/timing_test_report.json`
- 调试脚本：`backend/tests/browser/test_mu_extraction_timing.py`
