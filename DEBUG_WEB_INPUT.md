# Web端输入对话无响应问题调试指南

## 快速诊断步骤

### 1. 打开浏览器开发者工具（F12）

### 2. 检查Console标签
查看是否有任何红色错误信息，特别是：
- `Uncaught TypeError`
- `Failed to fetch`
- `ReferenceError`

### 3. 检查Network标签
1. 切换到Network标签
2. 在输入框中输入测试消息（如"测试"）并点击发送
3. 查看是否有对 `http://localhost:8000/api/agent/analyze` 的POST请求
   - **如果没有请求**：问题在前端事件处理
   - **如果有请求但失败**：查看响应状态码和错误信息

### 4. 在Console中运行调试命令

#### 检查store状态
```javascript
// 检查store是否正常
window.__vue_devtools_global_hook__?.apps?.[0]?._instance?.appContext?.app?.config?.globalProperties?.$store
```

#### 检查isAssistantReady状态
```javascript
// 检查助手是否ready
document.querySelector('.input-wrapper')?.__vueParentComponent?.isAssistantReady
```

#### 手动触发发送事件
```javascript
// 找到InputBox组件并手动调用handleSend
const inputBox = document.querySelector('textarea')?.__vueParentComponent
if (inputBox && inputBox.handleSend) {
  console.log('手动调用handleSend')
  inputBox.handleSend()
} else {
  console.error('找不到handleSend方法')
}
```

### 5. 启用详细日志

在Console中运行：
```javascript
// 启用Vue DevTools详细日志
localStorage.setItem('vue-devtools-debug', 'true')

// 刷新页面后，所有handleEvent调用都会打印详细日志
```

## 常见问题排查

### 问题1：点击发送后没有任何反应
**可能原因**：
- `isAssistantReady` 返回false
- JavaScript错误阻止了事件执行
- `handleSend` 函数未被正确绑定

**解决方案**：
```javascript
// 在Console中检查
console.log('activeAssistant:', activeAssistant)
console.log('isAssistantReady:', isAssistantReady)
```

### 问题2：用户消息显示但无响应
**可能原因**：
- 后端请求失败
- SSE流未正确处理
- `handleEvent` 方法未正确路由消息

**解决方案**：
1. 检查Network标签中的响应
2. 在Console中查看handleEvent日志

### 问题3：浏览器控制台有CORS错误
**可能原因**：
- 前端和后端端口不匹配
- CORS配置问题

**解决方案**：
检查 `.env` 文件中的 `VITE_API_BASE_URL` 配置

## 临时绕过方案

如果急需使用，可以直接访问后端API：
```bash
curl -X POST http://localhost:8000/api/agent/analyze \
  -H "Content-Type: application/json" \
  -d '{"query": "你的问题", "max_iterations": 10}'
```

## 报告问题时请提供

1. 浏览器控制台的完整错误信息（截图或文本）
2. Network标签中请求的详细信息（请求头、响应头、状态码）
3. 使用的浏览器类型和版本
4. 是否在社交模式（微信/QQ）中正常工作
