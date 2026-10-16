/**
 * 用户登录态。
 *
 * token 的物理存储在 utils/auth.js（供 axios 拦截器复用），
 * store 只负责内存中的用户信息、权限点与菜单树。
 */

import { defineStore } from 'pinia'

import { getProfile, login as loginApi, logout as logoutApi } from '@/api'
import { clearToken, getToken, setToken } from '@/utils/auth'

export const useUserStore = defineStore('user', {
  state: () => ({
    token: getToken(),
    /** 后端返回的用户信息：{ id, username, nickname, deptId, deptName, isSuper, roles } */
    userInfo: null,
    /** 操作权限点列表，如 ['knowledge:import', ...]；超管为 ['*'] */
    perms: [],
    /** 后端按权限裁剪后的菜单树（仅目录与菜单，不含按钮） */
    menus: [],
    /** 是否已拉取过用户信息（避免每次路由跳转都请求） */
    loaded: false,
  }),

  getters: {
    isLogin: (state) => Boolean(state.token),
    isSuper: (state) => Boolean(state.userInfo?.isSuper),
    displayName: (state) => state.userInfo?.nickname || state.userInfo?.username || '',
  },

  actions: {
    /** 登录：成功后写入 token（后续用户信息由路由守卫统一拉取） */
    async login(payload) {
      const data = await loginApi(payload)
      setToken(data.token)
      this.token = data.token
      if (data.userInfo) {
        this.applyProfile(data.userInfo)
      }
      return data
    },

    /** 拉取当前用户信息（含权限点与菜单树），已加载则直接复用 */
    async loadProfile(force = false) {
      if (this.loaded && !force) return this.userInfo
      const data = await getProfile()
      this.applyProfile(data)
      return data
    },

    applyProfile(profile) {
      this.userInfo = profile || null
      this.perms = profile?.perms || []
      this.menus = profile?.menus || []
      this.loaded = true
    },

    /** 是否拥有某个操作权限点；超管恒为 true；空权限点视为不需要鉴权 */
    hasPerm(perm) {
      if (!perm) return true
      if (this.isSuper) return true
      return this.perms.includes(perm)
    },

    /** 是否拥有其中任意一个权限点 */
    hasAnyPerm(perms) {
      const list = Array.isArray(perms) ? perms : [perms]
      return list.some((perm) => this.hasPerm(perm))
    },

    /** 清空本地登录态（不调用后端，用于凭证失效场景） */
    reset() {
      clearToken()
      this.token = ''
      this.userInfo = null
      this.perms = []
      this.menus = []
      this.loaded = false
    },

    /** 主动退出登录 */
    async logout() {
      try {
        if (this.token) await logoutApi()
      } catch {
        // 登出接口失败不阻断本地清理
      } finally {
        this.reset()
      }
    },
  },
})
