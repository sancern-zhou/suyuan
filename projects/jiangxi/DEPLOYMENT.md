# 江西项目前端部署

本说明仅适用于 `jiangxi` 项目。前端项目类型由构建时的 `PROJECT` 环境变量决定，
不会根据 Git 分支名自动选择。部署时必须显式设置 `PROJECT=jiangxi`。

## 后端会话数据库

江西部署的会话历史必须保存在本地 PostgreSQL。后端按以下优先级选择
会话数据库：`SESSION_DATABASE_URL`、`DATABASE_URL`。
生产环境必须显式设置本地 `SESSION_DATABASE_URL`，避免共享层的
`DATABASE_URL` 更新影响会话历史。`LOCAL_DATABASE_URL` 不再参与会话数据库选择。
知识库数据库由 `KNOWLEDGE_DATABASE_URL` 配置，未设置时使用 `DATABASE_URL`。

## 构建

```bash
cd /home/xckj/suyuan/frontend
PROJECT=jiangxi npm run build:standalone
```

禁止省略 `PROJECT=jiangxi`，否则 Vite 会使用 `default` 项目配置生成正式静态资源。

## 构建产物检查

```bash
grep -F '<title>江西省噪声智能分析平台</title>' /home/xckj/suyuan/frontend/dist/index.html
grep -R 'project:"jiangxi"' /home/xckj/suyuan/frontend/dist/assets
grep -R "resources?presentation_type=document" /home/xckj/suyuan/frontend/dist/assets
! grep -R "/office-documents" /home/xckj/suyuan/frontend/dist/assets
! grep -R "/visualizations" /home/xckj/suyuan/frontend/dist/assets
```

以上检查全部通过后，重新加载正式 Nginx：

```bash
docker exec suyuan-nginx nginx -s reload
curl -fsS http://127.0.0.1:5174/ | grep -F '<title>江西省噪声智能分析平台</title>'
```

## 复用噪声平台登录态（SSO）

溯源通过「一次性签名票据 + 跳转」复用噪声平台的登录态，用户无需二次登录。

### 溯源侧配置

`backend/.env`（web 与 worker 必须一致）：

```bash
AUTH_EXTRA_SYS_CODES=NOISE          # 额外接受浏览器带来的噪声平台 SysCode
AUTH_PLATFORM_SYS_CODES=JCXT,NOISE  # 复核上游 token 时依次尝试
SSO_SHARED_SECRET=<与噪声平台约定的长随机串>
SSO_TICKET_TTL_SECONDS=60
SSO_SESSION_TTL_SECONDS=28800
SSO_DEFAULT_ROLES=viewer
```

`SSO_SHARED_SECRET` 为空时 `/api/auth/sso/exchange` 返回 404（整体禁用）。
票据一次性校验依赖 Redis（`REDIS_*`），Redis 不可用时交换失败（fail closed）。

### 噪声平台侧签发

票据为 `base64url(payload) + "." + base64url(HMAC-SHA256(secret, payload_b64))`，
`payload` 为 JSON：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `u` | 是（或 `t`） | 用户 ID |
| `n` | 否 | 用户名，缺省用 `u` |
| `d` | 否 | 显示名，缺省用 `n` |
| `r` | 否 | 角色码数组，为空时用 `SSO_DEFAULT_ROLES` |
| `t` | 否 | 上游访问令牌；存在时溯源会先向认证服务复核身份，以防伪造 |
| `e` | 是 | 过期时间（Unix 秒），必须 ≤ 当前时间 + `SSO_TICKET_TTL_SECONDS` |
| `j` | 是 | 唯一票据 ID（如 uuid4），用于防重放 |

签名示例（Python）：

```python
import base64, hashlib, hmac, json, time, uuid

def sign_ticket(secret: str, *, uid: str, name: str, roles: list[str], ttl: int = 60) -> str:
    payload = {"u": uid, "n": name, "r": roles, "e": int(time.time()) + ttl, "j": str(uuid.uuid4())}
    enc = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).rstrip(b"=")
    sig = base64.urlsafe_b64encode(hmac.new(secret.encode(), enc, hashlib.sha256).digest()).rstrip(b"=")
    return f"{enc.decode()}.{sig.decode()}"
```

跳转目标：`https://<溯源域名>/sso?ticket=<票据>&redirect=/`（`redirect` 可选，仅接受站内绝对路径）。
前端在 `/sso` 调用 `POST /api/auth/sso/exchange` 换取本地会话令牌并写入
`Access-Token`/`Access-Sys-Code`/`Access-User`，随后跳转。

