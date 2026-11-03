import { createRouter, createWebHistory } from 'vue-router'
import ReactAnalysisView from '@/views/ReactAnalysisView.vue'
import FetchersView from '@/views/FetchersView.vue'
import KnowledgeBaseView from '@/views/KnowledgeBaseView.vue'
import ToolsManagementView from '@/views/ToolsManagementView.vue'
import SkillsManagementView from '@/views/SkillsManagementView.vue'
import SocialAccountsView from '@/views/SocialAccountsView.vue'
import ExpertDeliberationView from '@/views/ExpertDeliberationView.vue'
import LoginView from '@/views/LoginView.vue'
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
      path: '/social-accounts',
      name: 'social-accounts',
      component: SocialAccountsView,
      meta: { title: '社交账号管理', requiredModule: 'legacy' }
    },
    {
      path: '/expert-deliberation',
      name: 'expert-deliberation',
      component: ExpertDeliberationView,
      meta: { title: '专家会商推演', requiredModule: 'legacy' }
    },
    {
      // 兜底：总系统(统一鉴权平台)菜单跳转可能携带任意 defaultRoute 路径，
      // 统一回首页并保留 query/hash，避免入口 token/授权码丢失
      path: '/:pathMatch(.*)*',
      redirect: to => ({ path: '/', query: to.query, hash: to.hash })
    }
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: filterProjectRoutes(routes, projectConfig.hasModule)
})

export default router
