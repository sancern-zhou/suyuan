# Company Captcha Login Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Vue 3 standalone login page use the approved company SM2/SM4 implementation and complete the image-captcha login protocol.

**Architecture:** Keep authentication in the browser and company authentication service. Add focused SM2/SM4 modules, a pure captcha challenge builder, and explicit captcha fields in the existing auth API; the Vue page owns only form state and refresh behavior.

**Tech Stack:** Vue 3, Vite 5, Node test runner, `sm-crypto`, `gm-crypt`, UUID, Playwright

---

## File Structure

- Create `frontend/src/auth/SM2.js`: company SM2 C1C3C2 encryption adapter.
- Create `frontend/src/auth/SM4.js`: company SM4-CBC encryption/decryption adapter.
- Create `frontend/src/auth/companyCipher.test.mjs`: protocol compatibility tests for the two modules.
- Create `frontend/src/auth/captcha.js`: pure captcha key and URL generation.
- Create `frontend/src/auth/captcha.test.mjs`: deterministic captcha URL tests.
- Modify `frontend/src/auth/companyCrypto.js`: consume the approved modules instead of runtime key injection.
- Modify `frontend/src/auth/companyCrypto.test.mjs`: verify captcha and audit fields are carried into the encrypted login request.
- Modify `frontend/src/auth/authApi.js`: pass only the explicit captcha fields to `loginRequest`.
- Modify `frontend/src/views/LoginView.vue`: render, refresh, validate, and submit image captcha.
- Modify `frontend/index.html`: remove the missing runtime-config script.
- Delete `frontend/public/suyuan-runtime-config.example.js`: remove the obsolete deployment path.

### Task 1: Approved SM2 and SM4 Modules

**Files:**
- Create: `frontend/src/auth/SM2.js`
- Create: `frontend/src/auth/SM4.js`
- Create: `frontend/src/auth/companyCipher.test.mjs`
- Modify: `frontend/src/auth/companyCrypto.js`

- [ ] **Step 1: Write the failing cipher compatibility tests**

```js
import assert from 'node:assert/strict'
import test from 'node:test'

import { encryptSM2 } from './SM2.js'
import { decryptSM4, encryptSM4 } from './SM4.js'

test('SM2 output uses an unprefixed C1C3C2 cipher', () => {
  const encrypted = encryptSM2('ScGuanLy')
  assert.match(encrypted, /^[0-9a-f]+$/i)
  assert.equal(encrypted.length, 192 + Buffer.byteLength('ScGuanLy') * 2)
})

test('SM4 uses the company CBC configuration and round trips UTF-8', () => {
  const value = 'SUYUAN-溯源'
  const encrypted = encryptSM4(value)
  assert.notEqual(encrypted, value)
  assert.equal(decryptSM4(encrypted), value)
})
```

- [ ] **Step 2: Run the test and verify RED**

Run: `cd frontend && node --test src/auth/companyCipher.test.mjs`

Expected: FAIL with `ERR_MODULE_NOT_FOUND` for `SM2.js` or `SM4.js`.

- [ ] **Step 3: Add the Vite-compatible SM2 module**

```js
import smCrypto from 'sm-crypto'

const CIPHER_MODE_C1C3C2 = 1
const PUBLIC_KEY = '046644e1cb17328239b1cd1926758ab2dc69f9fbf896dab65e693a107fb48e9799a0814d45f3ce051b5823aa9a4bee8677efab57ff145c9caa9d2160ea31bc0fb8'

export function encryptSM2(data) {
  return smCrypto.sm2.doEncrypt(data, PUBLIC_KEY, CIPHER_MODE_C1C3C2)
}
```

- [ ] **Step 4: Add the Vite-compatible SM4 module**

```js
import gmCrypt from 'gm-crypt'

const SECRET_KEY = 'GJwsXX_BzW=gJWJW'
const cipher = new gmCrypt.sm4({
  key: SECRET_KEY,
  mode: 'cbc',
  iv: SECRET_KEY,
  cipherType: 'base64'
})

export const encryptSM4 = data => cipher.encrypt(data)
export const decryptSM4 = data => cipher.decrypt(data)
```

- [ ] **Step 5: Refactor `companyCrypto.js` to consume the modules**

```js
import { encryptSM2 } from './SM2.js'
import { encryptSM4 } from './SM4.js'

export function createCompanyCrypto(config, dependencies = {}) {
  const sm2Encrypt = dependencies.sm2Encrypt || encryptSM2
  const sm4Encrypt = dependencies.sm4Encrypt || encryptSM4
  // Keep the existing SM3, timestamp, UUID, password and signing layout.
}
```

Remove `defaultSm4Encrypt`, runtime public-key checks, and runtime `sm2PublicKey`/`sm4Key` use. Call `sm2Encrypt(value)` because the approved SM2 module owns the fixed mode and public key. Update the existing deterministic test doubles and expected strings from the old three-argument `sm2Encrypt(value, key, mode)` signature to the new unary signature.

- [ ] **Step 6: Run cipher and existing auth tests**

Run: `cd frontend && node --test src/auth/companyCipher.test.mjs src/auth/companyCrypto.test.mjs`

Expected: all tests PASS.

- [ ] **Step 7: Commit the cipher modules**

```bash
git add frontend/src/auth/SM2.js frontend/src/auth/SM4.js frontend/src/auth/companyCipher.test.mjs frontend/src/auth/companyCrypto.js
git commit -m "fix: use company SM2 and SM4 login modules"
```

### Task 2: Captcha Challenge Builder

**Files:**
- Create: `frontend/src/auth/captcha.js`
- Create: `frontend/src/auth/captcha.test.mjs`

- [ ] **Step 1: Write deterministic failing captcha tests**

```js
import assert from 'node:assert/strict'
import test from 'node:test'

import { createCaptchaChallenge } from './captcha.js'

test('captcha challenge replaces the previous key and uses company type 1', () => {
  const challenge = createCaptchaChallenge({
    previousKey: 'old key',
    authBaseUrl: '/api',
    uuid: () => 'new-key',
    random: () => 0,
    now: () => 123
  })
  assert.equal(challenge.key, 'new-key')
  assert.equal(challenge.url, '/api/auth/token/captcha?oldKey=old+key&key=new-key&type=1&d=123')
})

test('captcha challenge uses company type 3 for the upper random bucket', () => {
  const challenge = createCaptchaChallenge({
    previousKey: '', authBaseUrl: '/api', uuid: () => 'key', random: () => 0.9, now: () => 456
  })
  assert.match(challenge.url, /type=3&d=456$/)
})
```

- [ ] **Step 2: Run the test and verify RED**

Run: `cd frontend && node --test src/auth/captcha.test.mjs`

Expected: FAIL with `ERR_MODULE_NOT_FOUND` for `captcha.js`.

- [ ] **Step 3: Implement the pure challenge builder**

```js
import { v4 as uuidv4 } from 'uuid'

export function createCaptchaChallenge({
  previousKey = '',
  authBaseUrl = '/api',
  uuid = uuidv4,
  random = Math.random,
  now = Date.now
} = {}) {
  const key = uuid()
  const type = random() < 0.5 ? 1 : 3
  const params = new URLSearchParams({ oldKey: previousKey, key, type: String(type), d: String(now()) })
  return { key, url: `${authBaseUrl}/auth/token/captcha?${params}` }
}
```

- [ ] **Step 4: Run captcha tests**

Run: `cd frontend && node --test src/auth/captcha.test.mjs`

Expected: 2 tests PASS.

- [ ] **Step 5: Commit the captcha builder**

```bash
git add frontend/src/auth/captcha.js frontend/src/auth/captcha.test.mjs
git commit -m "feat: build company captcha challenges"
```

### Task 3: Login Request and Vue Form

**Files:**
- Modify: `frontend/src/auth/companyCrypto.test.mjs`
- Modify: `frontend/src/auth/companyCrypto.js`
- Modify: `frontend/src/auth/authApi.js`
- Modify: `frontend/src/views/LoginView.vue`

- [ ] **Step 1: Add a failing request-body test**

Add to `frontend/src/auth/companyCrypto.test.mjs`:

```js
test('company login includes captcha and login audit fields', () => {
  const crypto = createCompanyCrypto(
    { encryptType: 'SM2' },
    {
      sm2Encrypt: value => `sm2:${value}`,
      sm3Hash: value => `sm3:${value}`,
      sm4Encrypt: value => `sm4:${value}`,
      now: () => 1,
      uuid: () => 'uuid'
    }
  )
  const request = crypto.loginRequest('user', 'password', '', {
    verifyCode: '2468', captchaKey: 'captcha-key', isLog: '1', logType: '5'
  })
  assert.deepEqual(request.body, {
    secretName: 'sm2:user',
    secretCode: 'sm2:password',
    isEncry: true,
    verifyCode: '2468',
    captchaKey: 'captcha-key',
    isLog: '1',
    logType: '5'
  })
})
```

- [ ] **Step 2: Run the test and verify RED**

Run: `cd frontend && node --test src/auth/companyCrypto.test.mjs`

Expected: FAIL because captcha and audit fields are absent.

- [ ] **Step 3: Carry explicit login metadata through the crypto adapter**

```js
loginRequest(username, plainPassword, token = '', loginMetadata = {}) {
  return {
    body: {
      secretName: sm2Encrypt(username),
      secretCode: password(plainPassword),
      isEncry: true,
      verifyCode: loginMetadata.verifyCode,
      captchaKey: loginMetadata.captchaKey,
      isLog: '1',
      logType: '5'
    },
    headers: requestHeaders('/auth/token/authentication', token)
  }
}
```

- [ ] **Step 4: Pass captcha fields from `authApi.login`**

```js
async login({ username, password, verifyCode, captchaKey }) {
  const existing = session()
  const request = crypto.loginRequest(username, password, existing.token, { verifyCode, captchaKey })
  // Keep the existing POST, SysCode header and response handling.
}
```

- [ ] **Step 5: Add captcha state and refresh behavior to `LoginView.vue`**

```js
import { onMounted, ref } from 'vue'
import { createCaptchaChallenge } from '@/auth/captcha.js'

const verifyCode = ref('')
const captchaKey = ref('')
const captchaUrl = ref('')

function refreshCaptcha() {
  const challenge = createCaptchaChallenge({ previousKey: captchaKey.value, authBaseUrl: '/api' })
  captchaKey.value = challenge.key
  captchaUrl.value = challenge.url
  verifyCode.value = ''
}

onMounted(refreshCaptcha)
```

Add a required, four-character `verifyCode` input and clickable captcha image. Pass `verifyCode` and `captchaKey` to `auth.login`. In the `catch` block call `refreshCaptcha()` after displaying the server message.

- [ ] **Step 6: Run all auth tests**

Run: `cd frontend && npm run test:auth`

Expected: all auth tests PASS, including new cipher, captcha and login-body tests.

- [ ] **Step 7: Commit login captcha behavior**

```bash
git add frontend/src/auth/companyCrypto.js frontend/src/auth/companyCrypto.test.mjs frontend/src/auth/authApi.js frontend/src/views/LoginView.vue
git commit -m "feat: add company captcha login flow"
```

### Task 4: Remove Obsolete Runtime Config and Verify Deployment

**Files:**
- Modify: `frontend/index.html`
- Delete: `frontend/public/suyuan-runtime-config.example.js`

- [ ] **Step 1: Add a source-level failing check**

Run:

```bash
rg -n "suyuan-runtime-config" frontend/index.html frontend/public
```

Expected: matches in both `index.html` and the example file.

- [ ] **Step 2: Remove the obsolete script and example**

Delete `<script src="/suyuan-runtime-config.js"></script>` from `frontend/index.html` and delete `frontend/public/suyuan-runtime-config.example.js`.

- [ ] **Step 3: Verify obsolete references are gone**

Run: `rg -n "suyuan-runtime-config" frontend/index.html frontend/public`

Expected: exit 1 with no matches.

- [ ] **Step 4: Run the complete frontend verification**

```bash
cd frontend
npm run test:auth
npm run test:event-tasks
npm run build
```

Expected: all tests PASS and Vite exits 0.

- [ ] **Step 5: Run browser acceptance without logging secrets**

Use Playwright against `http://127.0.0.1:5174/login?redirect=/` and verify:

- `/api/auth/token/captcha` returns 200 with an image content type.
- Submitting the form sends one POST to `/api/auth/token/authentication`.
- The request body and Access Token are never printed.
- A wrong captcha displays the company error and changes `captchaKey`.
- With a valid captcha, the supplied test account reaches current-user lookup and redirects, or reports the exact next company-side requirement such as two-factor authentication.

- [ ] **Step 6: Commit cleanup**

```bash
git add frontend/index.html frontend/public/suyuan-runtime-config.example.js
git commit -m "chore: remove obsolete auth runtime config"
```

- [ ] **Step 7: Final repository and live checks**

Run:

```bash
git diff --check
git status --short --branch
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:5174/api/auth/token/captcha?key=smoke-test&type=1
```

Expected: diff check clean; only the pre-existing untracked `NormCraftAI/` remains; captcha returns 200.
