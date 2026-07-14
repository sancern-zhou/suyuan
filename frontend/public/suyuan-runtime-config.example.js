// Copy to suyuan-runtime-config.js during deployment and inject real client protocol values.
window.__SUYUAN_AUTH_CONFIG__ = {
  sysCode: 'SUYUAN',
  authBaseUrl: '/api',
  encryptType: 'SM2',
  sm2PublicKey: 'REPLACE_AT_DEPLOYMENT',
  sm4Key: 'REPLACE_AT_DEPLOYMENT'
}
