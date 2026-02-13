import { createRouter, createWebHistory } from 'vue-router'
import AnalysisView from '@/views/AnalysisView.vue'
import ReactAnalysisView from '@/views/ReactAnalysisView.vue'
import FetchersView from '@/views/FetchersView.vue'
import MapTestView from '@/views/MapTestView.vue'
import KnowledgeBaseView from '@/views/KnowledgeBaseView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'analysis',
      component: ReactAnalysisView
    },
    {
      path: '/classic',
      name: 'analysis-classic',
      component: AnalysisView
    },
    {
      path: '/session/:id',
      name: 'session',
      component: ReactAnalysisView,
      props: true
    },
    {
      path: '/fetchers',
      name: 'fetchers',
      component: FetchersView
    },
    {
      path: '/map-test',
      name: 'map-test',
      component: MapTestView
    },
    {
      path: '/knowledge-base',
      name: 'knowledge-base',
      component: KnowledgeBaseView,
      meta: { title: '知识库管理' }
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/'
    }
  ]
})

export default router
