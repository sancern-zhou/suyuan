# 微信QR码显示增强方案

## 问题分析

当前实现：
- QR码通过 `qr.print_ascii()` 在终端打印
- 仅在启动服务的终端可见
- 后台运行或日志重定向时无法查看

## 解决方案

### 方案1：QR码保存为图片（推荐）

**优点**：
- 可通过API访问
- 前端可以显示
- 可保存到本地

**实现**：

1. 修改 `weixin.py` 添加QR码图片保存：

```python
def _save_qr_code_image(url: str, save_path: Path) -> None:
    """Save QR code as image file."""
    try:
        import qrcode as qr_lib

        # Create QR code
        qr = qr_lib.QRCode(
            version=1,
            error_correction=qr_lib.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(url)
        qr.make(fit=True)

        # Save as image
        img = qr.make_image(fill_color="black", back_color="white")
        img.save(save_path)

        logger.info("QR code saved", path=str(save_path))
    except Exception as e:
        logger.warning("Failed to save QR code image", error=str(e))
```

2. 在 `_qr_login()` 中调用：

```python
async def _qr_login(self) -> bool:
    # Fetch QR code
    qrcode_id, scan_url = await self._fetch_qr_code()

    # Save QR code image
    qr_dir = self._get_state_dir() / "qrcode"
    qr_dir.mkdir(parents=True, exist_ok=True)
    qr_path = qr_dir / f"qrcode_{qrcode_id}.png"
    self._save_qr_code_image(scan_url, qr_path)

    # Also print to terminal
    self._print_qr_code(scan_url)

    # Store QR code path for API access
    self._current_qr_code_path = qr_path
    self._current_qr_code_id = qrcode_id

    # ... rest of login logic
```

3. 添加API端点获取QR码：

```python
# 在 app/routers/social_routes.py 添加

@router.get("/weixin/qrcode")
async def get_weixin_qrcode():
    """Get current WeChat login QR code."""
    try:
        from app.channels.manager import get_channel_manager

        manager = get_channel_manager()
        if not manager:
            raise HTTPException(status_code=404, detail="Channel manager not found")

        weixin_channel = manager.channels.get("weixin")
        if not weixin_channel:
            raise HTTPException(status_code=404, detail="WeChat channel not found")

        qr_path = getattr(weixin_channel, "_current_qr_code_path", None)
        if not qr_path or not qr_path.exists():
            raise HTTPException(status_code=404, detail="No QR code available")

        # Return image
        from fastapi.responses import FileResponse
        return FileResponse(qr_path, media_type="image/png")

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get QR code", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
```

### 方案2：前端显示QR码（最佳用户体验）

**前端组件**：

```vue
<template>
  <div class="weixin-qr-panel">
    <h3>微信登录</h3>

    <div v-if="qrCodeUrl" class="qr-code-container">
      <img :src="qrCodeUrl" alt="微信登录QR码" />
      <p>请使用微信扫描二维码登录</p>
      <p class="status">{{ status }}</p>
    </div>

    <div v-else class="loading">
      <p>正在生成登录二维码...</p>
    </div>

    <div class="actions">
      <button @click="refreshQRCode">刷新二维码</button>
      <button @click="checkStatus">检查状态</button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'

const qrCodeUrl = ref('')
const status = ref('等待扫描')

const fetchQRCode = async () => {
  try {
    const response = await fetch('/api/social/weixin/qrcode')
    const blob = await response.blob()
    qrCodeUrl.value = URL.createObjectURL(blob)
  } catch (error) {
    console.error('Failed to fetch QR code:', error)
  }
}

const checkStatus = async () => {
  try {
    const response = await fetch('/api/social/weixin/status')
    const data = await response.json()
    status.value = data.status

    if (data.logged_in) {
      status.value = '登录成功！'
      // 可以关闭弹窗或跳转
    }
  } catch (error) {
    console.error('Failed to check status:', error)
  }
}

const refreshQRCode = () => {
  qrCodeUrl.value = ''
  fetchQRCode()
}

onMounted(() => {
  fetchQRCode()

  // 轮询检查登录状态
  const interval = setInterval(() => {
    checkStatus()
  }, 3000)

  // 清理定时器
  onUnmounted(() => {
    clearInterval(interval)
  })
})
</script>

<style scoped>
.weixin-qr-panel {
  padding: 20px;
  text-align: center;
}

.qr-code-container img {
  width: 300px;
  height: 300px;
  margin: 20px auto;
  display: block;
}

.status {
  font-weight: bold;
  color: #666;
}

.actions {
  margin-top: 20px;
}

.actions button {
  margin: 0 10px;
  padding: 10px 20px;
}
</style>
```

### 方案3：简单临时方案（立即可用）

**查看终端QR码**：

1. **前台运行服务**（可以看到QR码）：
```bash
cd /home/xckj/suyuan/backend
python -m uvicorn app.main:app --reload --log-level info
```

2. **查看日志文件**：
```bash
# 查看最新的日志（包含QR码）
tail -f logs/app.log | grep -A 20 "QR code"
```

3. **检查QR码是否生成**：
```bash
# 查看QR码目录
ls -lah backend_data_registry/social/weixin/qrcode/

# 如果有QR码图片，可以直接查看
```

## 推荐实施方案

**阶段1**（立即）：
- 确保服务前台运行以查看QR码
- 或查看日志文件中的QR码 ASCII打印

**阶段2**（可选）：
- 实现QR码保存为图片
- 添加API端点访问QR码

**阶段3**（完整体验）：
- 添加前端QR码显示组件
- 支持实时登录状态更新

## 立即可用的方法

### 方法1：前台运行查看QR码

```bash
cd /home/xckj/suyuan/backend
python -m uvicorn app.main:app --reload
```

然后在终端中查找QR码打印（类似这样）：
```
██████████████████████████████
██████████████████████████████
████  ████  ████  █  █  █  ███
████  ████  ████  █  █  █  ███
████  ████  ████  █  █  █  ███
██████████████████████████████
```

### 方法2：使用日志查看

```bash
# 启动服务
cd /home/xckj/suyuan/backend
python -m uvicorn app.main:app > /tmp/server.log 2>&1 &

# 查看日志（包含QR码）
cat /tmp/server.log | grep -A 30 "QR code"
```

### 方法3：直接访问登录URL（备选）

如果实在无法显示QR码，可以从日志中找到登录URL：
```bash
tail -100 logs/app.log | grep "Login URL"
```

然后在手机上直接访问该URL（可能需要在微信中打开）。

## 需要实现增强功能吗？

如果您需要我实现以下功能，请告诉我：
1. ✅ QR码保存为图片文件
2. ✅ API端点访问QR码
3. ✅ 前端组件显示QR码

我可以立即为您实现这些增强功能！
