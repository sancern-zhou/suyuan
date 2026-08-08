import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router/index'
import { useAuthStore } from './auth/authStore.js'
import { installAuthGuard } from './auth/routerGuard.js'
import { initializeAuthStore } from './auth/runtimeConfig.js'
import { registerVitePreloadRecovery } from './services/vitePreloadRecovery.js'
import './styles/main.scss'

registerVitePreloadRecovery()

async function bootstrapApplication() {
  const app = createApp(App)
  const pinia = createPinia()

  app.use(pinia)
  const authStore = useAuthStore(pinia)
  await initializeAuthStore(authStore)
  installAuthGuard(router, authStore)
  app.use(router)
  app.mount('#app')
}


bootstrapApplication()
