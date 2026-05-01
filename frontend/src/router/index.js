import { createRouter, createWebHistory } from 'vue-router'
import ReactAnalysisView from '@/views/ReactAnalysisView.vue'
import FetchersView from '@/views/FetchersView.vue'
import KnowledgeBaseView from '@/views/KnowledgeBaseView.vue'
import ToolsManagementView from '@/views/ToolsManagementView.vue'
import SkillsManagementView from '@/views/SkillsManagementView.vue'
import SocialAccountsView from '@/views/SocialAccountsView.vue'
import ExpertDeliberationView from '@/views/ExpertDeliberationView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
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
      component: FetchersView
    },
    {
      path: '/knowledge-base',
      name: 'knowledge-base',
      component: KnowledgeBaseView,
      meta: { title: '知识库管理' }
    },
    {
      path: '/tools-management',
      name: 'tools-management',
      component: ToolsManagementView,
      meta: { title: '工具管理' }
    },
    {
      path: '/skills-management',
      name: 'skills-management',
      component: SkillsManagementView,
      meta: { title: '技能管理' }
    },
    {
      path: '/social-accounts',
      name: 'social-accounts',
      component: SocialAccountsView,
      meta: { title: '社交账号管理' }
    },
    {
      path: '/expert-deliberation',
      name: 'expert-deliberation',
      component: ExpertDeliberationView,
      meta: { title: '专家会商推演' }
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/'
    }
  ]
})

export default router
