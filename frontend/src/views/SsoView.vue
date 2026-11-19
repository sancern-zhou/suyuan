<template>
  <main class="sso-page">
    <section class="sso-card" aria-live="polite">
      <p class="eyebrow">SUYUAN AGENT</p>
      <h1>{{ failed ? '无法自动登录' : '正在复用平台登录…' }}</h1>
      <p class="hint">
        {{ failed ? failed : '正在验证噪声平台登录票据，请稍候。' }}
      </p>
      <button v-if="failed" type="button" @click="goLogin">使用账号密码登录</button>
    </section>
  </main>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '@/auth/authStore.js'
import { safeRedirect } from '@/auth/routerGuard.js'
import { exchangeSsoTicket, normalizeSsoExchange } from '@/auth/sso.js'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const failed = ref('')

function goLogin() {
  void router.replace({ path: '/login', query: { redirect: safeRedirect(route.query.redirect) } })
}

onMounted(async () => {
  const ticket = typeof route.query.ticket === 'string' ? route.query.ticket : ''
  if (!ticket) {
    failed.value = '缺少外部登录票据。'
    return
  }
  try {
    const payload = await exchangeSsoTicket({ ticket })
    const session = normalizeSsoExchange(payload, auth.sysCode || 'SUYUAN')
    await auth.adoptSession(session)
    await router.replace(safeRedirect(route.query.redirect))
  } catch (reason) {
    failed.value = reason?.message || '外部登录校验失败。'
  }
})
</script>

<style scoped>
.sso-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 32px 20px;
  background: var(--bg-layout);
}
.sso-card {
  width: min(430px, 100%);
  padding: 42px;
  border: 1px solid rgba(13, 125, 131, 0.14);
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 24px 70px rgba(13, 75, 88, 0.14);
  text-align: center;
}
.eyebrow { margin: 0 0 8px; color: var(--color-primary-active); font-size: 12px; font-weight: 800; letter-spacing: 0.16em; }
h1 { margin: 0; color: #173b43; font-size: 24px; }
.hint { margin: 14px 0 0; color: #668087; line-height: 1.65; }
button { margin-top: 22px; padding: 12px 18px; border: 0; border-radius: 11px; color: white; background: var(--gradient-brand); font: inherit; font-weight: 750; cursor: pointer; }
</style>
