# 微信二维码时序问题修复 - V2

## 问题

前端在快速重试（生成多个临时账号ID），说明API调用失败或超时。

## 根本原因

`_qr_login()` 方法会**阻塞并等待用户扫码完成**，导致API响应超时。

## 解决方案

### 1. 拆分二维码登录流程

**新增方法**：`_init_qr_login()`
- 只生成二维码，不等待扫码
- 立即返回二维码ID

**新增方法**：`_wait_for_qr_scan(qrcode_id)`
- 等待已有二维码的扫码状态
- 不生成新二维码

**修改方法**：`start()`
- 检查是否已有二维码
- 如果有，调用 `_wait_for_qr_scan()` 继续等待
- 如果没有，调用 `_qr_login()` 生成新的

### 2. 修改 auto-create API 流程

```python
# 1. 创建渠道实例
channel = manager._create_weixin_channel(temp_account)

# 2. 后台任务：初始化HTTP客户端并启动
async def login_and_start():
    # 初始化HTTP客户端
    channel._client = httpx.AsyncClient(...)
    channel._running = True

    # 只生成二维码，不等待扫码
    qrcode_id = await channel._init_qr_login()

    # 启动轮询（start会检测已有二维码并继续等待）
    await channel.start()

asyncio.create_task(login_and_start())

# 3. 等待二维码就绪（最多5秒）
await asyncio.wait_for(channel._qr_code_ready.wait(), timeout=5.0)

# 4. 返回响应
return {"account_id": ..., "status": "created"}
```

## 时序图

```
前端           API            渠道               微信API
 |              |               |                   |
 | POST /auto-create            |                   |
 |------------->|               |                   |
 |              | create channel                   |
 |              |--------------->|                   |
 |              | init_qr_login()                  |
 |              |               | fetch_qrcode()    |------->
 |              |               |                   |<-------
 |              |               | save_qr_code()    |
 |              |               | [设置 _qr_code_ready] |
 |              | wait for ready|                   |
 |              |<--------------|                   |
 | 200 OK       |               |                   |
 |<-------------|               |                   |
 |              |               | start() (后台)    |
 |              |               | wait_for_qr_scan()|
 |              |               | [轮询扫码状态]    |
 | GET /qrcode |               |                   |
 |------------->|               |                   |
 | 200 (图片)   |               |                   |
 |<-------------|               |                   |
 |              |               | [用户扫码]        |
 |              |               | [登录成功]        |
 |              |               | save_state()      |
```

## 关键改进

1. **API快速响应**：不等待扫码，只等待二维码生成（~1秒）
2. **避免重复生成二维码**：`start()` 检测已有二维码，继续等待
3. **后台异步处理**：扫码等待在后台任务中进行

## 测试步骤

1. **重启后端**（确保代码已加载）
   ```bash
   cd /home/xckj/suyuan/backend
   pkill -f "uvicorn app.main:app"
   python -m uvicorn app.main:app --reload --port 8000
   ```

2. **清除旧账号**（可选）
   ```bash
   vim backend/config/social_config.yaml
   # 删除 auto_* 开头的临时账号
   ```

3. **前端测试**
   - 刷新社交账号管理页面
   - 点击"扫码添加微信"
   - 观察是否**立即显示二维码**（第一次就成功）

4. **检查日志**
   ```
   creating_weixin_channel        # 创建渠道
   channel_created                  # 渠道创建成功
   starting_login_async             # 启动异步登录任务
   qrcode_generated                 # 二维码生成成功
   qrcode_ready                     # 二维码就绪
   temp_account_auto_created        # 账号创建成功
   ```

## 预期结果

✅ **第一次就能看到二维码**
- API响应时间 < 2秒
- 二维码图片正常显示
- 不再需要刷新第二次

✅ **扫码后自动完成登录**
- 后台任务检测到扫码
- 自动保存token
- 进入正常运行状态

## 文件修改清单

1. `backend/app/channels/weixin.py`
   - 新增 `_init_qr_login()` 方法
   - 新增 `_wait_for_qr_scan()` 方法
   - 修改 `start()` 方法，检测已有二维码

2. `backend/app/api/social_account_routes.py`
   - 修改 `auto_create_account()` API
   - 添加 `httpx` 导入

## 故障排查

如果仍有问题，检查：

1. **后端日志**
   - 查找 `qrcode_ready_timeout`（二维码生成超时）
   - 查找 `qrcode_generation_failed`（二维码生成失败）

2. **前端控制台**
   - 查找 `500` 错误（API失败）
   - 查找 `404` 错误（二维码未生成）

3. **状态文件**
   - 检查 `backend_data_registry/social/weixin/{account_id}/qrcode/` 目录
   - 确认二维码图片文件存在
