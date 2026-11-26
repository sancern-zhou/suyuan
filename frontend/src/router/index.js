import { createRouter, createWebHistory, createWebHashHistory } from 'vue-router'
import ReactAnalysisView from '@/views/ReactAnalysisView.vue'
import FetchersView from '@/views/FetchersView.vue'
import KnowledgeBaseView from '@/views/KnowledgeBaseView.vue'
import ToolsManagementView from '@/views/ToolsManagementView.vue'
import SkillsManagementView from '@/views/SkillsManagementView.vue'
import ExpertDeliberationView from '@/views/ExpertDeliberationView.vue'
import LoginView from '@/views/LoginView.vue'
import SsoView from '@/views/SsoView.vue'
import { projectConfig } from '@/config/projectConfig.js'
import { filterProjectRoutes } from './projectRoutes.js'

const routes = [
    {
      path: '/login',
      name: 'login',
      component: LoginView,
      meta: { public: true, title: '登录' }
    },
    {
      path: '/sso',
      name: 'sso',
      component: SsoView,
      meta: { public: true, title: '平台免登录' }
    },
    {
      path: '/bigscreen',
      name: 'bigscreen',
      component: () => import('@/views/xuchang/BigScreenView.vue'),
      meta: {
        requiredModule: 'xuchang-air-quality',
        title: '数据大屏',
        allowDashboardToken: true
      }
    },
    {
      path: '/mobile-map',
      name: 'mobile-map',
      component: () => import('@/views/xuchang/MobileMapView.vue'),
      meta: {
        requiredModule: 'xuchang-air-quality',
        title: '实时地图',
        allowDashboardToken: true,
        adminOnly: true
      }
    },
    {
      path: '/fieldwatch',
      name: 'fieldwatch',
      component: () => import('@/views/xuchang/FieldWatchView.vue'),
      meta: {
        requiredModule: 'xuchang-air-quality',
        title: '现场巡查快报（测试）',
        allowDashboardToken: true,
        adminOnly: true
      }
    },
    {
      path: '/',
      name: 'analysis',
      component: ReactAnalysisView
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
      component: FetchersView,
      meta: { requiredModule: 'legacy' }
    },
    {
      path: '/knowledge-base',
      name: 'knowledge-base',
      component: KnowledgeBaseView,
      meta: { title: '知识库管理', requiredModule: 'legacy' }
    },
    {
      path: '/tools-management',
      name: 'tools-management',
      component: ToolsManagementView,
      meta: { title: '工具管理', requiredModule: 'legacy' }
    },
    {
      path: '/skills-management',
      name: 'skills-management',
      component: SkillsManagementView,
      meta: { title: '技能管理', requiredModule: 'legacy' }
    },
    {
      path: '/expert-deliberation',
      name: 'expert-deliberation',
      component: ExpertDeliberationView,
      meta: { title: '专家会商推演', requiredModule: 'legacy' }
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/'
    }
]

const router = createRouter({
  history: import.meta.env.BASE_URL === './'
    ? createWebHashHistory()
    : createWebHistory(import.meta.env.BASE_URL),
  routes: filterProjectRoutes(routes, projectConfig.hasModule)
})

export default router
