import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router/index'
import { useAuthStore } from './auth/authStore.js'
import { installAuthGuard } from './auth/routerGuard.js'
import './styles/main.scss'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
installAuthGuard(router, useAuthStore(pinia))
app.use(router)

app.mount('#app')
