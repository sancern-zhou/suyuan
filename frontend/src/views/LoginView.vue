<template>
  <main class="login-page">
    <section class="login-card" aria-labelledby="login-title">
      <div class="brand-mark">
        <img src="/wechat-screenshot.png" alt="溯源智能体" />
      </div>
      <div class="login-copy">
        <p class="eyebrow">SUYUAN AGENT</p>
        <h1 id="login-title">登录溯源智能体</h1>
        <p>使用公司统一账号进入。若您已从公司平台登录，将自动复用当前会话。</p>
      </div>

      <form @submit.prevent="submit">
        <label for="username">账号</label>
        <input
          id="username"
          v-model.trim="username"
          autocomplete="username"
          required
          :disabled="auth.loading"
        />

        <label for="password">密码</label>
        <input
          id="password"
          v-model="password"
          type="password"
          autocomplete="current-password"
          required
          :disabled="auth.loading"
        />

        <label for="verify-code">验证码</label>
        <div class="captcha-row">
          <input
            id="verify-code"
            v-model.trim="verifyCode"
            autocomplete="off"
            maxlength="4"
            required
            :disabled="auth.loading"
          />
          <button
            class="captcha-refresh"
            type="button"
            title="看不清，换一张"
            aria-label="刷新验证码"
            :disabled="auth.loading"
            @click="refreshCaptcha"
          >
            <img v-if="captchaUrl" :src="captchaUrl" alt="验证码图片" />
            <span v-else>刷新验证码</span>
          </button>
        </div>

        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <button type="submit" :disabled="auth.loading || !username || !password || !verifyCode">
          {{ auth.loading ? '正在验证…' : '登录' }}
        </button>
      </form>
    </section>
  </main>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '@/auth/authStore.js'
import { createCaptchaChallenge } from '@/auth/captcha.js'
import { safeRedirect } from '@/auth/routerGuard.js'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const username = ref('')
const password = ref('')
const verifyCode = ref('')
const captchaKey = ref('')
const captchaUrl = ref('')
const error = ref('')

function refreshCaptcha() {
  const challenge = createCaptchaChallenge({
    previousKey: captchaKey.value,
    authBaseUrl: '/api'
  })
  captchaKey.value = challenge.key
  captchaUrl.value = challenge.url
  verifyCode.value = ''
}

async function submit() {
  error.value = ''
  try {
    await auth.login({
      username: username.value,
      password: password.value,
      verifyCode: verifyCode.value,
      captchaKey: captchaKey.value
    })
    await router.replace(safeRedirect(route.query.redirect))
  } catch (reason) {
    error.value = reason?.message || '登录失败，请检查账号和密码'
    refreshCaptcha()
  } finally {
    password.value = ''
  }
}

onMounted(refreshCaptcha)
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 32px 20px;
  background:
    radial-gradient(circle at 18% 20%, rgba(0, 215, 174, 0.18), transparent 32%),
    radial-gradient(circle at 82% 80%, rgba(0, 117, 214, 0.2), transparent 34%),
    #f5faf9;
}

.login-card {
  width: min(430px, 100%);
  padding: 42px;
  border: 1px solid rgba(13, 125, 131, 0.14);
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 24px 70px rgba(13, 75, 88, 0.14);
}

.brand-mark {
  width: 68px;
  height: 68px;
  overflow: hidden;
  border-radius: 18px;
  box-shadow: 0 10px 24px rgba(0, 151, 161, 0.2);
}

.brand-mark img { width: 100%; height: 100%; object-fit: cover; }
.login-copy { margin: 24px 0 30px; }
.eyebrow { margin: 0 0 8px; color: #008f91; font-size: 12px; font-weight: 800; letter-spacing: 0.16em; }
h1 { margin: 0; color: #173b43; font-size: 28px; }
.login-copy > p:last-child { margin: 12px 0 0; color: #668087; line-height: 1.65; }
form { display: grid; gap: 10px; }
label { margin-top: 8px; color: #31565e; font-size: 14px; font-weight: 650; }
input {
  width: 100%;
  box-sizing: border-box;
  padding: 13px 14px;
  border: 1px solid #c8d9dc;
  border-radius: 10px;
  outline: none;
  font: inherit;
}
input:focus { border-color: #009a9e; box-shadow: 0 0 0 3px rgba(0, 154, 158, 0.12); }
.captcha-row { display: grid; grid-template-columns: minmax(0, 1fr) 132px; gap: 10px; }
.captcha-refresh {
  height: 48px;
  margin: 0;
  padding: 0;
  overflow: hidden;
  border: 1px solid #c8d9dc;
  border-radius: 10px;
  color: #31565e;
  background: #f4f9fa;
}
.captcha-refresh img { display: block; width: 100%; height: 100%; object-fit: cover; }
button {
  margin-top: 14px;
  padding: 14px;
  border: 0;
  border-radius: 11px;
  color: white;
  background: linear-gradient(120deg, #00a982, #007fc4);
  font: inherit;
  font-weight: 750;
  cursor: pointer;
}
button:disabled { cursor: wait; opacity: 0.58; }
.error { margin: 8px 0 0; color: #c13a3a; font-size: 14px; }

@media (max-width: 520px) {
  .login-card { padding: 30px 24px; border-radius: 18px; }
}
</style>
