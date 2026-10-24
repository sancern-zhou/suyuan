// 生成 Cube REST API 的 JWT(有效期默认 24h)
// 用法: node gen-token.js [secret]
// 缺省取环境变量 CUBEJS_API_SECRET, 其次 local.json 的 apiSecret(该文件不进代码仓库)。
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const local = (() => {
  try {
    return JSON.parse(fs.readFileSync(path.join(__dirname, 'local.json'), 'utf8'));
  } catch {
    return {};
  }
})();

const secret = process.argv[2] || process.env.CUBEJS_API_SECRET || local.apiSecret;
if (!secret) {
  console.error('missing secret — pass as arg, set CUBEJS_API_SECRET, or configure local.json apiSecret');
  process.exit(1);
}

const b64url = (buf) => Buffer.from(buf).toString('base64url');
const header = b64url(JSON.stringify({ alg: 'HS256', typ: 'JWT' }));
const payload = b64url(JSON.stringify({ exp: Math.floor(Date.now() / 1000) + 86400 }));
const sig = crypto.createHmac('sha256', secret).update(`${header}.${payload}`).digest('base64url');
console.log(`${header}.${payload}.${sig}`);
