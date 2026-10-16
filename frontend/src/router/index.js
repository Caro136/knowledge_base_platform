/**
 * 路由与访问守卫。
 *
 * 路由的 path / meta.perm 与后端 seed（app/seed.py）中的菜单定义保持一致；
 * 侧边栏菜单由后端 /api/auth/me 返回的菜单树渲染（见 layout/Layout.vue），
 * 本文件的静态路由表用于解析组件与做权限兜底拦截。
 */

import { ElMessage } from 'element-plus'
import { createRouter, createWebHistory } from 'vue-router'

import Layout from '@/layout/Layout.vue'
import { useUserStore } from '@/store/user'

export const APP_TITLE = '知识库管理平台'

export const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
    meta: { public: true, title: '登录' },
  },
  {
    path: '/',
    component: Layout,
    redirect: '/dashboard/index',
    children: [
      {
        path: 'dashboard/index',
        name: 'Dashboard',
        component: () => import('@/views/dashboard/Index.vue'),
        meta: { title: '运营看板', perm: 'dashboard:view' },
      },
      {
        path: 'knowledge/list',
        name: 'KnowledgeList',
        component: () => import('@/views/knowledge/List.vue'),
        meta: { title: '知识单元', perm: 'knowledge:list' },
      },
      {
        path: 'chat/index',
        name: 'Chat',
        component: () => import('@/views/chat/Index.vue'),
        meta: { title: '智能问答', perm: 'ai:chat' },
      },
      {
        path: 'precipitation/faq',
        name: 'Faq',
        component: () => import('@/views/precipitation/Faq.vue'),
        meta: { title: 'FAQ 审核', perm: 'faq:list' },
      },
      {
        path: 'precipitation/gap',
        name: 'Gap',
        component: () => import('@/views/precipitation/Gap.vue'),
        meta: { title: '知识缺口', perm: 'gap:list' },
      },
      {
        path: 'system/user',
        name: 'SysUser',
        component: () => import('@/views/system/User.vue'),
        meta: { title: '用户管理', perm: 'user:list' },
      },
      {
        path: 'system/role',
        name: 'SysRole',
        component: () => import('@/views/system/Role.vue'),
        meta: { title: '角色管理', perm: 'role:list' },
      },
      {
        path: 'system/dept',
        name: 'SysDept',
        component: () => import('@/views/system/Dept.vue'),
        meta: { title: '部门管理', perm: 'dept:list' },
      },
    ],
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: () => import('@/views/error/NotFound.vue'),
    meta: { public: true, title: '页面不存在' },
  },
]

/** 取当前用户第一个有权访问的页面路径，作为越权跳转的落点 */
function firstAllowedPath(store) {
  const children = routes.find((item) => item.path === '/')?.children || []
  const hit = children.find((child) => !child.meta?.perm || store.hasPerm(child.meta.perm))
  return hit ? `/${hit.path}` : ''
}

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

router.beforeEach(async (to) => {
  const store = useUserStore()
  document.title = to.meta.title ? `${to.meta.title} - ${APP_TITLE}` : APP_TITLE

  // 公开页面
  if (to.meta.public) {
    // 已登录用户访问登录页：直接送回系统首页
    if (to.path === '/login' && store.isLogin) {
      return { path: firstAllowedPath(store) || '/' }
    }
    return true
  }

  if (!store.isLogin) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }

  // 拉取用户信息（含权限点与菜单）；失败说明凭证已失效
  try {
    await store.loadProfile()
  } catch {
    store.reset()
    return { path: '/login' }
  }

  const landing = firstAllowedPath(store)
  if (!landing) {
    // 账号未绑定任何有权限的角色
    store.reset()
    ElMessage.error('当前账号未分配任何可访问的功能权限，请联系管理员')
    return { path: '/login' }
  }

  if (to.meta.perm && !store.hasPerm(to.meta.perm)) {
    ElMessage.warning('无权访问该页面，已为你跳转到可访问的页面')
    return { path: landing }
  }

  return true
})

export default router
