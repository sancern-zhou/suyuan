// guangdong-cube — 广东运维语义层(Cube Core, Apache-2.0 开源核心)
// 口径唯一定义在 schema/*.js; 智能体/前端经 /cubejs-api/v1/load 取数, 不再裸写 SQL。
// 连库用 agent_reader(只读, 仅 guangdong_mart, statement_timeout 15s) — 与智能体
// SQL 护栏同权限, 语义层不引入任何额外数据库权限。
// 只监听 127.0.0.1(内网本机消费; 后端/前端代理都在本机)。
// 端口 4611: 与江苏语义层(4610)共存于同一台 Windows 运行时, 互不冲突。
//
// 版本说明: 用 0.35.x 线(纯 JS 编译器)。1.7.x 的 schema 编译强依赖 @cubejs-backend/native
// 二进制(GitHub releases 下载, 本机直连断), 且 CLI 要求 Node 22。
// 坑(重装必读, 详见江苏 cube/README.md): node_modules 需 --ignore-scripts 安装;
// production 模式必须设 CUBEJS_CACHE_AND_QUEUE_DRIVER=memory; FileRepository 路径必须相对。
const fs = require('fs');
const path = require('path');
const express = require('express');
const { CubejsServerCore, FileRepository } = require('@cubejs-backend/server-core');
const PostgresDriver = require('@cubejs-backend/postgres-driver');

// 密钥不落代码仓库: 优先环境变量, 其次本地 local.json(已 gitignore, 模板见 local.example.json)。
const local = (() => {
  try {
    return JSON.parse(fs.readFileSync(path.join(__dirname, 'local.json'), 'utf8'));
  } catch {
    return {};
  }
})();

const API_SECRET = process.env.CUBEJS_API_SECRET || local.apiSecret;
const DB_PASSWORD = process.env.AGENT_READER_PASSWORD || local.dbPassword;
// 库名按部署环境配置（local.json 的 database 键；本机为 suyuan_app）
const DB_DATABASE = process.env.CUBEJS_DB_NAME || local.database || 'suyuan_app';
if (!API_SECRET || !DB_PASSWORD) {
  console.error('[guangdong-cube] missing apiSecret/dbPassword — configure cube/local.json or env');
  process.exit(1);
}

const app = express();
app.use(express.json({ limit: '10mb' }));

const core = new CubejsServerCore({
  dbType: 'postgres',
  apiSecret: API_SECRET,
  driverFactory: () => new PostgresDriver({
    host: '127.0.0.1',
    port: process.env.CUBEJS_DB_PORT ? Number(process.env.CUBEJS_DB_PORT) : 5433,
    user: 'agent_reader',
    password: DB_PASSWORD,
    database: DB_DATABASE,
  }),
  // FileRepository 内部会与 process.cwd() 拼接, 必须传相对路径(启动脚本固定 cd 到本项目)
  repositoryFactory: () => new FileRepository('schema'),
});

core.initApp(app);

const port = process.env.PORT || 4611;
app.listen(port, '127.0.0.1', () => {
  // eslint-disable-next-line no-console
  console.log(`[guangdong-cube] semantic layer listening on http://127.0.0.1:${port}/cubejs-api/v1/load`);
});
