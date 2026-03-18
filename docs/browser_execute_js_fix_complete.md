# 浏览器工具 execute_js 修复完成报告

## 问题概述

从后端日志 `D:\溯源\docs\后端日志.md` 发现百度搜索结果mu属性提取失败：

```
error: Page.evaluate: ReferenceError: arguments is not defined
```

## 根本原因

1. **技能指南错误示例** - 使用了`arguments[0]`获取refs参数
2. **execute_js工具缺陷** - 未实现refs参数传递
3. **Playwright箭头函数** - 不支持`arguments`对象

---

## 修复内容

### 1. 技能指南更新 (v3.3)

文件：`backend/app/tools/browser/browser_skills_guide.md`

**主要更新**：

#### 新增百度mu属性提取专门章节
- **方法1：直接DOM提取** (⭐⭐⭐⭐⭐ 强烈推荐)
- **方法2：混合方法** (⭐⭐⭐⭐)
- **方法3：refs参数** (⭐⭐⭐ 高级用法)

#### 新增 "Execute JS 使用规范" 章节
```python
# 无参数版本（最常用）
browser(action="execute_js", code="""
    () => {
        return document.title;
    }
""")

# 带参数版本（高级用法）
browser(action="execute_js", code="""
    (param) => {
        return param;
    }
""", refs=value)
```

#### 新增常见任务示例
1. 点击被遮挡的元素
2. 移除遮挡对话框
3. 提取页面数据
4. 滚动到页面底部

#### 新增重要约束
- 禁止使用`arguments[0]`
- 必须使用箭头函数或函数声明
- 返回值必须是JSON可序列化

#### 新增错误恢复指南
```
错误：arguments is not defined
原因：使用了 arguments[0] 获取参数
解决：使用函数参数 (param) => { ... } 并传递参数
```

#### 更新禁止项列表
```
❌ .btn, .el-button, .ant-btn, button, input, div
❌ 并发浏览器操作
❌ execute_js中使用 arguments[0]  ⚠️ 新增禁止项
```

### 2. execute_js工具增强

文件：`backend/app/tools/browser/actions/execute_js.py`

**功能更新**：

```python
# 新增refs参数支持
if refs is not None:
    # 执行JavaScript并传递refs参数
    result = page.evaluate(f"(refs) => {{ {code} }}", refs)
    refs_provided = True
else:
    # 向后兼容：不传递参数
    result = page.evaluate(f"() => {{ {code} }}")
    refs_provided = False
```

**返回值增强**：
```python
return {
    "code": code,
    "result": result,
    "type": result_type,
    "refs_provided": refs_provided  # 新增：是否使用了refs参数
}
```

**日志增强**：
- 添加`browser_execute_js_with_refs`日志事件
- 记录refs_count和refs_provided状态

### 3. 验证测试

文件：`backend/tests/browser/test_execute_js_fix.py`

**测试覆盖**：
1. ✅ 直接DOM提取 (无refs，最简单)
2. ✅ refs参数支持 (高级用法)
3. ✅ 向后兼容 (无参数调用)
4. ✅ 旧代码失败验证 (arguments错误按预期出现)

---

## 测试结果

```
[SUCCESS] All tests passed!

1. Direct DOM Extraction     [OK] - 找到6个结果，10ms响应
2. Refs Parameter Support    [OK] - 参数传递成功
3. Backward Compatibility    [OK] - 现有代码无需修改
4. Old Code Fails            [OK] - 错误代码按预期失败
```

---

## 使用指南

### 推荐做法：直接DOM提取

```python
# 百度搜索结果mu属性提取
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

### 高级用法：refs参数

```python
# 需要详细元素信息时使用
snapshot = browser(action="snapshot", format="ai", compact=True)
refs = snapshot['data']['refs']

browser(action="execute_js", code="""
    (refs) => {
        for (const [refId, refData] of Object.entries(refs)) {
            if (refData.html_attrs && refData.html_attrs.mu) {
                return refData.html_attrs.mu;
            }
        }
        return null;
    }
""", refs=refs)  # 必须传递refs参数
```

---

## 禁止的错误用法

```python
# ❌ 错误：使用arguments[0]
browser(action="execute_js", code="""
    () => {
        const refs = arguments[0];  # 会导致 "arguments is not defined" 错误
    }
""")

# ❌ 错误：期望refs自动注入
browser(action="execute_js", code="""
    () => {
        for (const [refId, refData] of Object.entries(refs)) {  # refs未定义
            // ...
        }
    }
""")
```

---

## 文件变更清单

### 修改的文件
1. `backend/app/tools/browser/browser_skills_guide.md` (v3.2 → v3.3)
   - 新增：百度mu属性提取专门章节
   - 新增：Execute JS 使用规范
   - 新增：常见任务示例
   - 新增：重要约束
   - 新增：错误恢复指南
   - 更新：禁止项列表
   - 更新：选择器优先级

2. `backend/app/tools/browser/actions/execute_js.py`
   - 新增：refs参数支持
   - 新增：refs_provided返回字段
   - 增强：日志记录
   - 保持：向后兼容性

### 新增的文件
1. `backend/tests/browser/test_mu_extraction_methods.py`
   - 方法对比测试脚本
   - 4种测试方法对比

2. `backend/tests/browser/test_execute_js_fix.py`
   - 修复验证测试脚本
   - 4个测试用例全部通过

3. `docs/execute_js_mu_fix_report.md`
   - 修复报告
   - 方法对比分析

4. `docs/browser_execute_js_fix_complete.md`
   - 完整修复报告（本文件）

---

## 版本更新

| 组件 | 旧版本 | 新版本 |
|------|--------|--------|
| browser_skills_guide.md | v3.2 | v3.3 |
| execute_js.py | v2.0 | v2.1 |

---

## 后续建议

### 立即生效
- ✅ 技能指南已更新
- ✅ execute_js工具已增强
- ✅ 验证测试已通过

### 可选优化
1. 更新tool.py中的浏览器工具description，引用技能指南
2. 添加更多execute_js使用示例到系统提示词
3. 考虑添加其他参数支持（如element参数）

---

## 总结

修复已完成并通过全部验证测试。核心改进：

1. **技能指南全面更新** - 移除错误示例，添加正确用法
2. **execute_js工具增强** - 支持refs参数，保持向后兼容
3. **测试验证完成** - 4个测试用例全部通过
4. **文档完善** - 详细的使用指南和错误恢复方法

LLM现在可以正确使用直接DOM提取方法获取百度搜索结果的mu属性，不再出现`arguments is not defined`错误。

推荐LLM优先使用方法1（直接DOM提取），只有在需要详细元素信息时才使用refs参数方法。
