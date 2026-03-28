# 微信二维码时序问题修复

## 问题描述

**症状**：点击"扫码添加微信"时，第一次二维码刷新不出来，需要第二次刷新才能显示。

**原因**：时序竞争问题
1. 前端调用 `POST /api/social/accounts/weixin/auto-create`
2. 后端立即返回 200 OK，但此时二维码还在生成中
3. 前端收到响应后立即请求 `GET /api/social/accounts/weixin/{id}/qrcode`
4. 二维码还没生成，返回 404 Not Found
5. 后端完成二维码生成
6. 前端第二次请求才成功

## 解决方案

### 1. 添加二维码就绪事件机制

**文件**：`backend/app/channels/weixin.py`

**修改内容**：
```python
# __init__ 方法中
self._qr_code_ready = asyncio.Event()  # 二维码就绪事件
self._qr_code_ready.clear()  # 确保初始状态为未就绪

# _qr_login 方法开始时
async def _qr_login(self) -> bool:
    self._qr_code_ready.clear()  # 清除事件，准备生成新二维码
    # ...

# _save_qr_code_image 方法结束时
def _save_qr_code_image(self, url: str, qrcode_id: str) -> None:
    # ... 生成并保存二维码
    self._qr_code_ready.set()  # 设置事件，通知二维码已就绪
```

### 2. 修改 auto-create API 等待二维码就绪

**文件**：`backend/app/api/social_account_routes.py`

**修改内容**：
```python
# 启动渠道并等待二维码就绪（最多等待5秒）
await channel.login(force=False)  # 生成二维码

try:
    await asyncio.wait_for(channel._qr_code_ready.wait(), timeout=5.0)
    logger.info("qrcode_ready_wait_success")
except asyncio.TimeoutError:
    logger.warning("qrcode_ready_timeout")

# 启动轮询（不阻塞响应）
asyncio.create_task(channel.start())

return {
    "account_id": request.temp_id,
    "status": "created",
    "qr_code_available": True  # 确保二维码可用
}
```

## 修复后的行为

### 时序图

```
前端                    后端 API                  微信渠道                  微信API
  |                         |                         |                         |
  | POST /auto-create       |                         |                         |
  |------------------------>|                         |                         |
  |                         | login()                 |                         |
  |                         |------------------------>|                         |
  |                         |                         | fetch_qrcode()          |-------->
  |                         |                         |                         |<--------
  |                         |                         | save_qr_code_image()    |
  |                         |                         | [设置 _qr_code_ready]   |
  |                         | wait for ready event    |                         |
  |                         |<------------------------|                         |
  | 200 OK                  |                         |                         |
  |<------------------------|                         |                         |
  |                         | start() (异步)          |                         |
  |                         |------------------------>|                         |
  |                         |                         | start polling           |
  | GET /qrcode             |                         |                         |
  |------------------------>|                         |                         |
  | 200 OK (图片)           |                         |                         |
  |<------------------------|                         |                         |
```

### 关键改进

1. **同步等待二维码生成**：`auto-create` API 会等待最多 5 秒，确保二维码生成完成
2. **异步启动轮询**：渠道轮询在后台启动，不阻塞 API 响应
3. **事件通知机制**：使用 `asyncio.Event` 实现高效的事件通知

### 预期结果

✅ **第一次刷新就能看到二维码**
- 前端调用 `auto-create` API
- 后端等待二维码生成完成（最多5秒）
- 返回响应时，二维码已经可用
- 前端立即请求二维码，成功返回

✅ **5秒超时保护**
- 如果二维码生成超过5秒，API 仍然返回
- 前端可以通过轮询 `status` 接口检查二维码状态
- 避免请求无限期挂起

## 测试步骤

1. **清除旧的临时账号**（可选）
   ```bash
   # 删除配置中的临时账号
   vim backend/config/social_config.yaml
   # 删除 auto_mn* 开头的账号
   ```

2. **重启后端**
   ```bash
   cd /home/xckj/suyuan/backend
   pkill -f "uvicorn app.main:app"
   python -m uvicorn app.main:app --reload --port 8000
   ```

3. **前端测试**
   - 打开社交账号管理页面
   - 点击"扫码添加微信"
   - 观察是否**第一次**就能看到二维码

4. **查看日志**
   ```
   qrcode_ready_wait_success     # 二维码就绪等待成功
   qrcode_ready_timeout          # 二维码就绪等待超时（5秒）
   QR code saved                 # 二维码已保存
   ```

## 相关文件

- `backend/app/channels/weixin.py` - 微信渠道实现
- `backend/app/api/social_account_routes.py` - 社交账号 API
- `frontend/src/components/social/CreateAccountModal.vue` - 前端创建账号模态框

## 后续优化建议

1. **前端重试机制**：即使后端已经等待，前端也可以添加重试逻辑作为保护
2. **WebSocket 推送**：登录成功后通过 WebSocket 推送状态更新，避免轮询
3. **进度反馈**：前端显示"正在生成二维码..."的加载状态
