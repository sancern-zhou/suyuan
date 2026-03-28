# 二维码前端显示问题 - 修复指南

## 问题诊断

后端正常工作（二维码已生成），但前端无法显示。

## 🔧 解决方案

### 方案1：清除浏览器缓存（最常见原因）

**Chrome/Edge**:
1. 按 `Ctrl + Shift + Delete`
2. 选择"缓存的图片和文件"
3. 点击"清除数据"
4. 刷新页面 (`F5` 或 `Ctrl + R`)

**Firefox**:
1. 按 `Ctrl + Shift + Delete`
2. 选择"缓存"
3. 点击"立即清除"
4. 刷新页面

**或者强制刷新**:
- Windows: `Ctrl + F5` 或 `Ctrl + Shift + R`
- Mac: `Cmd + Shift + R`

### 方案2：重启前端开发服务器

```bash
# 1. 停止当前前端服务（按 Ctrl+C）

# 2. 清理Vite缓存
rm -rf node_modules/.vite

# 3. 重新启动
npm run dev
```

### 方案3：检查浏览器控制台错误

1. 按 `F12` 打开开发者工具
2. 切换到 `Console` 标签
3. 刷新页面
4. 查看是否有红色错误信息

**常见错误**:

#### 错误1: CORS错误
```
Access to XMLHttpRequest has been blocked by CORS policy
```
**解决**: 确保后端正在运行，CORS配置正确

#### 错误2: 404 Not Found
```
GET /api/social/accounts/weixin/auto_xxx/qrcode 404
```
**解决**: 检查账号ID是否正确，等待后端完全启动

#### 错误3: 网络错误
```
net::ERR_CONNECTION_REFUSED
```
**解决**: 检查后端是否正在运行

### 方案4：使用无痕/隐私模式测试

1. 打开新的无痕窗口：
   - Chrome: `Ctrl + Shift + N`
   - Firefox: `Ctrl + Shift + P`
2. 访问 `http://localhost:5174/social-accounts`
3. 点击"扫码添加微信"
4. 观察是否正常显示二维码

### 方案5：手动测试API

在浏览器地址栏输入：
```
http://localhost:8000/api/social/accounts/weixin/auto_mn87p4io/qrcode
```

**预期结果**: 浏览器直接显示二维码图片

如果看到图片 → 后端正常，问题在前端
如果404/错误 → 后端问题

## 🐛 调试步骤

### 1. 检查前端是否获取到账号ID

打开浏览器控制台（F12），在Console中输入：
```javascript
// 查看是否有错误
console.log('检查前端状态')
```

### 2. 检查网络请求

在开发者工具中：
1. 切换到 `Network` 标签
2. 点击"扫码添加微信"
3. 查看是否有以下请求：
   - `POST /api/social/accounts/weixin/auto-create`
   - `GET /api/social/accounts/weixin/auto_xxx/qrcode`

**检查响应**:
- `auto-create` 应该返回 200 和账号信息
- `qrcode` 应该返回 200 和图片数据

### 3. 添加调试日志

修改 `CreateAccountModal.vue`，添加更多console.log：

```javascript
const fetchQRCode = async () => {
  qrLoading.value = true
  console.log('开始获取二维码, accountId:', tempAccountId.value)

  try {
    const url = `/api/social/accounts/weixin/${tempAccountId.value}/qrcode`
    console.log('请求URL:', url)

    const response = await axios.get(url, { responseType: 'blob' })
    console.log('响应状态:', response.status)
    console.log('响应数据类型:', response.data.type)
    console.log('响应数据大小:', response.data.size)

    qrCodeUrl.value = URL.createObjectURL(response.data)
    console.log('Blob URL创建成功:', qrCodeUrl.value)

    loginStatus.value = 'waiting'
    startStatusCheck()
  } catch (error) {
    console.error('获取二维码失败:', error)
    console.error('错误详情:', error.response)
    errorMessage.value = error.message
  } finally {
    qrLoading.value = false
  }
}
```

### 4. 检查Vue DevTools

1. 安装Vue DevTools浏览器扩展
2. 打开Vue DevTools
3. 选择 `CreateAccountModal` 组件
4. 查看组件状态：
   - `tempAccountId`: 应该有值
   - `qrCodeUrl`: 应该是blob:URL
   - `qrLoading`: 应该是false
   - `errorMessage`: 应该是空

## ✅ 验证修复成功

修复后，你应该看到：

1. **点击"扫码添加微信"**
   - 弹出模态窗口
   - 显示"正在初始化..."

2. **几秒后**
   - 自动显示二维码图片
   - 下方显示"等待扫描..."

3. **控制台无错误**

## 🎯 最可能的原因

根据经验，最可能的原因是：

1. **浏览器缓存了旧版本的前端代码** (80%)
   - 解决: 强制刷新或清除缓存

2. **Vite开发服务器缓存问题** (15%)
   - 解决: 重启前端服务

3. **前端代码热更新失败** (5%)
   - 解决: 完全重启浏览器

## 📞 如果以上方案都不行

请提供以下信息：

1. 浏览器控制台的完整错误信息
2. Network标签中的请求/响应详情
3. 后端日志中的相关错误
4. 使用的浏览器和版本

---

**快速尝试（按顺序）**:
1. `Ctrl + Shift + R` 强制刷新
2. 关闭标签页，重新打开
3. 重启前端服务
4. 使用无痕模式测试
