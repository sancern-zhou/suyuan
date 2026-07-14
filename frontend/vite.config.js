import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  return {
    base: env.VITE_APP_BASE_PATH || '/',
    plugins: [vue()],
    resolve: {
      alias: {
        '@': resolve(__dirname, 'src')
      }
    },
    server: {
      port: 5174,
      host: '0.0.0.0',
      proxy: {
        '/api/auth': {
          target: env.VITE_AUTH_PROXY_TARGET || 'http://10.10.204.80:8025',
          changeOrigin: true,
          secure: false
        },
        '/api/suyuan/ws': {
          target: 'http://localhost:8000',
          changeOrigin: true,
          ws: true,
          rewrite: path => path.replace(/^\/api\/suyuan/, '')
        },
        '/api/suyuan': {
          target: 'http://localhost:8000',
          changeOrigin: true,
          secure: false,
          rewrite: path => path.replace(/^\/api\/suyuan/, '/api')
        },
        '/api': {
          target: 'http://localhost:8000',
          changeOrigin: true,
          secure: false
        }
      }
    }
  }
})
