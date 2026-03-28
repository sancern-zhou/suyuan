# 多微信账号支持 - 实施计划

## 📋 改造方案文档

详细设计文档：`backend/docs/multi_weixin_accounts_design.md`

## ✅ 已创建的文件

### 1. 配置文件
- ✅ `config/social_config.yaml` - 多微信账号配置文件
- ✅ `backend/config/social_config.py` - 配置模型和加载函数

### 2. API路由
- ✅ `backend/app/api/social_account_routes.py` - 账号管理API接口

### 3. 文档
- ✅ `backend/docs/multi_weixin_accounts_design.md` - 完整设计文档

## 🔨 待改造的核心文件

### Phase 1: 后端核心改造

#### 1.1 ChannelManager 改造
**文件**: `backend/app/channels/manager.py`

**改动要点**:
```python
# 改动前: channels: dict[str, BaseChannel] = {}
# 改动后: channels: dict[str, BaseChannel] = {}  # 格式: "weixin:account_1"

# 新增方法:
def _init_weixin_channels(self, weixin_config: WeixinConfig) -> None
def _create_weixin_channel(self, account_config: WeixinAccountConfig) -> WeixinChannel
```

#### 1.2 WeixinChannel 改造
**文件**: `backend/app/channels/weixin.py`

**改动要点**:
```python
# 新增参数:
def __init__(self, config: Any, bus: MessageBus, instance_id: str = None):
    self.instance_id = instance_id or "default"
    self.name = f"weixin:{self.instance_id}"

# 修改方法:
def _get_state_dir(self) -> Path:
    # 改为: backend_data_registry/social/weixin/{instance_id}/
```

#### 1.3 路由注册
**文件**: `backend/app/main.py`

**改动要点**:
```python
from app.api import social_account_routes

app.include_router(social_account_routes.router)
```

### Phase 2: 前端界面开发

#### 2.1 创建目录结构
```bash
frontend/src/components/social/
├── QRCodeModal.vue          # 二维码弹窗
├── CreateAccountModal.vue   # 创建账号弹窗
└── AccountCard.vue          # 账号卡片组件

frontend/src/views/
└── SocialAccountsView.vue   # 账号管理页面
```

#### 2.2 添加路由
**文件**: `frontend/src/router/index.js`

**改动要点**:
```javascript
import SocialAccountsView from '@/views/SocialAccountsView.vue'

{
  path: '/social-accounts',
  name: 'social-accounts',
  component: SocialAccountsView,
  meta: { title: '社交账号管理' }
}
```

#### 2.3 添加导航菜单
**文件**: `frontend/src/components/TopBar.vue` 或 `AssistantSidebar.vue`

**改动要点**:
```vue
<router-link to="/social-accounts">社交账号</router-link>
```

## 📝 实施步骤清单

### Step 1: 后端改造（1-2天）

- [ ] **1.1** 改造 `backend/app/channels/manager.py`
  - [ ] 修改 `_init_channels()` 支持多实例
  - [ ] 新增 `_init_weixin_channels()` 方法
  - [ ] 新增 `_create_weixin_channel()` 方法

- [ ] **1.2** 改造 `backend/app/channels/weixin.py`
  - [ ] 添加 `instance_id` 参数
  - [ ] 修改 `_get_state_dir()` 使用实例子目录
  - [ ] 修改 `bot_account` 属性返回值

- [ ] **1.3** 注册新路由
  - [ ] 在 `backend/app/main.py` 中导入并注册 `social_account_routes.router`

- [ ] **1.4** 测试后端API
  - [ ] 测试账号创建接口
  - [ ] 测试QR码获取接口
  - [ ] 测试状态查询接口

### Step 2: 前端开发（1-2天）

- [ ] **2.1** 创建组件目录
  - [ ] 创建 `frontend/src/components/social/` 目录

- [ ] **2.2** 创建页面组件
  - [ ] 创建 `SocialAccountsView.vue`
  - [ ] 创建 `QRCodeModal.vue`
  - [ ] 创建 `CreateAccountModal.vue`

- [ ] **2.3** 添加路由配置
  - [ ] 在 `frontend/src/router/index.js` 中添加路由

- [ ] **2.4** 添加导航入口
  - [ ] 在 `TopBar.vue` 或 `AssistantSidebar.vue` 中添加链接

### Step 3: 测试和优化（1天）

- [ ] **3.1** 功能测试
  - [ ] 测试单账号登录
  - [ ] 测试多账号并发登录
  - [ ] 测试消息路由（验证用户ID隔离）
  - [ ] 测试记忆存储隔离

- [ ] **3.2** 边界测试
  - [ ] 测试账号重复创建
  - [ ] 测试不存在的账号操作
  - [ ] 测试网络错误处理

- [ ] **3.3** 性能测试
  - [ ] 测试多账号同时运行时的资源占用
  - [ ] 测试大量消息并发处理

### Step 4: 部署和文档（0.5天）

- [ ] **4.1** 更新文档
  - [ ] 更新 `DEPLOYMENT_GUIDE.md`
  - [ ] 编写用户使用手册

- [ ] **4.2** 生产环境部署
  - [ ] 备份现有配置
  - [ ] 运行配置迁移脚本
  - [ ] 部署新版本

## 🚀 快速启动指南

### 1. 修改配置文件

编辑 `config/social_config.yaml`:

```yaml
weixin:
  enabled: true
  accounts:
    - id: "account_1"
      name: "客服机器人"
      enabled: true
      auto_start: true
```

### 2. 启动后端

```bash
cd backend
python -m uvicorn app.main:app --reload
```

### 3. 启动前端

```bash
cd frontend
npm run dev
```

### 4. 访问管理界面

打开浏览器访问: `http://localhost:5174/social-accounts`

## 📊 API接口列表

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/social/accounts` | 获取账号列表 |
| POST | `/api/social/accounts/weixin` | 创建微信账号 |
| GET | `/api/social/accounts/weixin/:id/qrcode` | 获取QR码 |
| GET | `/api/social/accounts/weixin/:id/status` | 获取状态 |
| POST | `/api/social/accounts/weixin/:id/start` | 启动账号 |
| POST | `/api/social/accounts/weixin/:id/stop` | 停止账号 |
| DELETE | `/api/social/accounts/weixin/:id` | 删除账号 |
| POST | `/api/social/accounts/weixin/:id/refresh-qrcode` | 刷新QR码 |

## ⚠️ 注意事项

1. **向后兼容**: 旧版单账号配置会自动迁移到新格式
2. **状态隔离**: 每个账号有独立的状态目录 `backend_data_registry/social/weixin/{instance_id}/`
3. **并发安全**: ChannelManager使用异步锁保证线程安全
4. **错误处理**: 所有API接口都有完善的错误处理和日志记录

## 🐛 已知问题

暂无

## 📞 技术支持

如有问题，请查看详细设计文档：`backend/docs/multi_weixin_accounts_design.md`

---

**预计完成时间**: 3-5个工作日
**当前状态**: 设计阶段完成，等待实施
