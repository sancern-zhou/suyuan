import './utils/polyfills.js'
import { installAccountStoreReset } from './auth/accountStoreReset.js'
import { discardLegacyConversationState, onAccountChanged, setAccountIdentity } from './auth/accountSession.js'
import { browserAuthStorage } from './auth/storage.js'
import { agentAPI } from './services/reactApi.js'
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router/index'
import { useAuthStore } from './auth/authStore.js'
import { installAuthGuard } from './auth/routerGuard.js'
import { normalizeSsoEntry } from './auth/ssoEntry.js'
import { initializeAuthStore } from './auth/runtimeConfig.js'
import { registerVitePreloadRecovery } from './services/vitePreloadRecovery.js'
import './styles/tokens.css'
import './styles/main.scss'
import './styles/components.scss'

registerVitePreloadRecovery()

async function bootstrapApplication() {
  // 独立部署构建使用 hash 路由：外部平台按 history 风格跳转 /sso?ticket=
  // 时先把入口改写成 #/sso?ticket=，否则票据会丢失。
  if (import.meta.env.BASE_URL === './') {
    normalizeSsoEntry(window.location, window.history)
  }
  const app = createApp(App)
  const pinia = createPinia()

  discardLegacyConversationState(window.localStorage)
  installAccountStoreReset(pinia, () => { void agentAPI.cancel() })
  app.use(pinia)
  const authStore = useAuthStore(pinia)
  onAccountChanged(() => {
    if (authStore.authMode !== 'mock' && !browserAuthStorage().readSession().token) {
      const initialized = authStore.initialized
      authStore.clear()
      if (initialized) void router.replace('/login')
    }
  })
  const authConfig = await initializeAuthStore(authStore)
  window.addEventListener('storage', event => {
    if (event.storageArea !== window.localStorage || (event.key && !event.key.startsWith('Access-'))) return
    const session = browserAuthStorage().readSession()
    setAccountIdentity(session.user, session.sysCode)
    authStore.configure(authConfig)
    if (!authStore.isAuthenticated) void router.replace('/login')
  })
  installAuthGuard(router, authStore)
  app.use(router)
  app.mount('#app')
}


bootstrapApplication()
