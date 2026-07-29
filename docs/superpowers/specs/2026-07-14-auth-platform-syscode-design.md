# 认证平台 SysCode 拆分设计

## 目标

将公司认证平台使用的应用代码与 Suyuan 自身业务系统代码分离：所有 `/api/auth/**` 调用以及后端 Token 用户查询使用 `JCXT`；所有 `/api/suyuan/**` 业务请求、Suyuan 后端入口校验、网关契约和 Nacos 元数据继续使用 `SUYUAN`。

## 已验证事实

- 相同账号、密码、验证码及国密协议下，登录请求携带 `SUYUAN` 返回 `state=131，未授权的应用访问`。
- 登录请求携带 `JCXT` 返回成功并签发 Token。
- 使用该 Token 和 `JCXT` 调用 `getCurrentUser` 返回成功用户信息。

## 代码职责

### 前端

- `authPlatformSysCode = JCXT`：只用于登录、当前用户和退出等公司认证接口。
- `businessSysCode = SUYUAN`：写入浏览器标准会话，并用于 Suyuan 业务 API 请求头。
- 登录成功后取得用户的 `getCurrentUser` 请求使用 `JCXT`；保存会话时仍保存 `SUYUAN`，确保业务请求和后端入口校验保持不变。

### 后端

- 现有 `AUTH_SYS_CODE=SUYUAN` 保持不变，继续校验浏览器经网关传入的业务请求头。
- 新增 `AUTH_PLATFORM_SYS_CODE=JCXT`，仅供 `PlatformAuthClient.get_current_user` 调用公司认证平台。
- 缓存中的标准用户仍标记为 Suyuan 业务代码 `SUYUAN`，不把上游认证应用代码扩散到业务授权模型。

### 网关与服务注册

- `/api/suyuan/**`、`suyuan-agent`、Nacos metadata 和网关契约无需修改。
- `/api/auth/**` 路由只负责透传前端给出的 `SysCode: JCXT`。

## 请求流程

1. 登录页向 `/api/auth/token/authentication` 发送 `SysCode: JCXT`。
2. 登录成功后向 `/api/auth/account/getCurrentUser` 发送 `SysCode: JCXT`。
3. 前端将 Token 与业务代码 `SUYUAN` 写入标准会话。
4. 业务请求向 `/api/suyuan/**` 发送 `SysCode: SUYUAN`。
5. Suyuan 后端确认入口代码为 `SUYUAN`，再使用 `JCXT` 向公司认证平台校验 Token。
6. 用户身份校验成功后，Suyuan 执行自身权限判断。

## 错误处理

- 公司认证接口返回 `130-134`、`401` 或 `403` 时，沿用现有认证失败处理。
- 业务请求携带非 `SUYUAN` 代码时，Suyuan 后端继续拒绝。
- `AUTH_PLATFORM_SYS_CODE` 缺失时默认 `JCXT`；部署模板显式写出该值，避免环境歧义。

## 测试与验收

- 前端测试断言登录、当前用户和退出均发送 `JCXT`。
- 前端测试断言登录后保存的业务会话仍为 `SUYUAN`。
- 后端测试断言入口 `SUYUAN` 被接受、其他代码被拒绝。
- 后端测试断言向公司认证平台查询用户时发送 `JCXT`。
- 现有鉴权、验证码、网关和业务权限测试继续通过。
- 实时登录验收应得到 Token，并继续触发 `getCurrentUser`；输出中不得打印密码、请求体或 Token。

## 范围边界

本次不更改品牌名称、业务 API 前缀、网关路由、Nacos serviceName、Redis结构或角色权限模型。
