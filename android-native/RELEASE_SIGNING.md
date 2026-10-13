# Android 正式签名治理

App 走内部分发（无应用商店），Android 规则是**同一把密钥签名的包才能覆盖安装**。
签名密钥一旦丢失，已装机用户永远无法覆盖更新，只能全量卸载重装（丢失本地登录态，
服务端会话数据不受影响）。本文档是密钥生成、保管、登记和发版校验的唯一依据。

## 一、正式密钥生成（一次性，由密钥保管人执行）

用 JDK 17 的 keytool 生成（本机 `PATH` 里的 java/keytool 是 JDK 11，必须用
`$JAVA_HOME/bin/keytool`，JAVA_HOME 指向 JDK 17）：

```bash
"$JAVA_HOME/bin/keytool" -genkeypair -v \
  -keystore suyuan-release.keystore -alias suyuan \
  -keyalg RSA -keysize 2048 -validity 10950 \
  -dname "CN=Suyuan Android, O=Xuchang, C=CN"
```

- 有效期 30 年（10950 天），密码必须强密码，**密码不经任何聊天工具/工单传递**。

## 二、保管规则

1. keystore 文件与密码**分开存放**，各自至少两份备份（如：受控服务器目录 + 离线介质；
   密码在密码管理器或受控文档）。
2. 不入 git（`.gitignore` 已排除 `*.jks`/`*.keystore` 和 `android-native/keystore.properties`），
   也不要放到项目目录内。
3. 登记持有人与存放位置；人员变动时交接并更新下表。

### 指纹与持有登记（生成后立即填写）

| 项目 | 值 |
| --- | --- |
| 证书 SHA-256 指纹 | （生成后填写：`keytool -list -v -keystore suyuan-release.keystore`） |
| 别名 | `suyuan` |
| keystore 存放位置 | （填写） |
| 密码存放位置 | （填写） |
| 保管人 | （填写） |
| 生成日期 | （填写） |

## 三、构建机配置

每台需要出包的机器：

```powershell
Copy-Item keystore.properties.example keystore.properties
# 编辑 keystore.properties，填入 storeFile/storePassword/keyAlias/keyPassword
```

配置后：**所有构建（含 debug）都用正式签名**，任何机器出的包都能互相覆盖安装；
未配置的机器只能编译 debug（回退调试签名，Gradle 会警告），release 构建直接报错拒绝——
这是刻意的 fail-fast，不允许调试签名包对外分发。

## 四、发版流程

```powershell
.\build-release.ps1 -VersionCode <递增整数> -VersionName "<x.y.z>" `
  -ExpectedCertSha256 <上表登记的指纹（去冒号小写）>
# 本机验证安装可加 -Install [-DeviceId <serial>]
```

Checklist：

1. `versionCode` 必须严格递增（低于已装机版本将无法覆盖安装）；`versionName` 同步可读化。
2. 脚本会自动跑 `apksigner verify` 并打印证书 SHA-256；传 `-ExpectedCertSha256` 时指纹不符会拒绝出包。
3. 分发前确认指纹与登记值一致；对外发布的包和指纹记录归档。
4. 前端有改动时，先在 `frontend/` 执行 `npm run build:standalone` 再出包（图表资源来自该构建）。

## 五、存量设备迁移（仅一次）

历史上用各开发机调试密钥签名的包，无法被正式包覆盖安装，需**卸载后重装一次**正式包。
迁移后所有后续版本走覆盖更新。App 服务端会话与聊天记录在服务器持久化，
重装只需重新登录。
