import { createRouter, createWebHistory } from 'vue-router'
import ReactAnalysisView from '@/views/ReactAnalysisView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'react-analysis',
      component: ReactAnalysisView
    }
  ]
})

export default router
