import { installAccountStoreReset } from './auth/accountStoreReset.js'
import { discardLegacyConversationState, onAccountChanged, setAccountIdentity } from './auth/accountSession.js'
import { browserAuthStorage } from './auth/storage.js'
import { agentAPI } from './services/reactApi.js'
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router/index'
import { useAuthStore, operationLoginUrl } from './auth/authStore.js'
import { installAuthGuard } from './auth/routerGuard.js'
import { initializeAuthStore } from './auth/runtimeConfig.js'
import { registerVitePreloadRecovery } from './services/vitePreloadRecovery.js'
import './styles/tokens.css'
import './styles/main.scss'
import './styles/components.scss'

registerVitePreloadRecovery()

async function bootstrapApplication() {
  const app = createApp(App)
  const pinia = createPinia()

  const redirectToOperationLogin = () => {
    const returnUrl = encodeURIComponent(
      window.location.pathname + window.location.search
    )
    // window.top escapes an ops-platform iframe so the login page takes over
    // the whole browser window.
    window.top.location.href = `${operationLoginUrl()}?ReturnUrl=${returnUrl}`
  }

  discardLegacyConversationState(window.localStorage)
  installAccountStoreReset(pinia, () => { void agentAPI.cancel() })
  app.use(pinia)
  const authStore = useAuthStore(pinia)
  onAccountChanged(() => {
    if (
      authStore.authMode !== 'mock' &&
      authStore.authMode !== 'operation' &&
      !browserAuthStorage().readSession().token
    ) {
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
    if (!authStore.isAuthenticated) {
      if (authConfig.authMode === 'operation') redirectToOperationLogin()
      else void router.replace('/login')
    }
  })
  installAuthGuard(router, authStore, {
    onOperationLoginRequired: redirectToOperationLogin
  })
  app.use(router)
  app.mount('#app')
}


bootstrapApplication()
