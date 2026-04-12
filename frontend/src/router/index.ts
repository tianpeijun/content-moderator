import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  { path: '/login', name: 'Login', component: () => import('../views/LoginPage.vue'), meta: { title: '登录', public: true } },
  { path: '/', redirect: '/rules' },
  { path: '/rules', name: 'Rules', component: () => import('../views/RulesPage.vue'), meta: { title: '规则管理' } },
  { path: '/prompt', name: 'Prompt', component: () => import('../views/PromptPage.vue'), meta: { title: '提示词预览与测试' } },
  { path: '/logs', name: 'Logs', component: () => import('../views/LogsPage.vue'), meta: { title: '审核日志' } },
  { path: '/test', name: 'Test', component: () => import('../views/TestPage.vue'), meta: { title: '批量测试' } },
  { path: '/test-records', name: 'TestRecords', component: () => import('../views/TestRecordsPage.vue'), meta: { title: '测试记录' } },
  { path: '/model-config', name: 'ModelConfig', component: () => import('../views/ModelConfigPage.vue'), meta: { title: '模型配置' } },
  { path: '/stats', name: 'Stats', component: () => import('../views/StatsPage.vue'), meta: { title: '数据统计' } },
  { path: '/labels', name: 'Labels', component: () => import('../views/LabelsPage.vue'), meta: { title: '标签管理' } },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// Navigation guard: redirect to /login if not authenticated
router.beforeEach((to, _from, next) => {
  const isPublic = to.meta?.public === true
  const token = localStorage.getItem('cognito_token')

  if (!isPublic && !token) {
    next({ name: 'Login' })
  } else if (to.name === 'Login' && token) {
    // Already logged in, skip login page
    next({ path: '/' })
  } else {
    next()
  }
})

export default router
