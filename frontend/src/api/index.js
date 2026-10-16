/**
 * 接口定义。
 *
 * 按后端模块分组，函数名与 SPEC §6.2 的接口清单一一对应；
 * 未实现的模块在对应任务中补充（见注释中的任务号）。
 *
 * 约定：request 拦截器已解包统一响应，调用方直接拿到 data。
 */

import request from './request'

// ---------------------------------------------------------------------------
// 认证与当前用户（T-05）
// ---------------------------------------------------------------------------

/** 登录：{ username, password } → { token, expiresIn, userInfo } */
export const login = (data) => request.post('/auth/login', data)

/** 登出（无状态 JWT，仅作语义标记） */
export const logout = () => request.post('/auth/logout')

/** 当前用户：含 id/username/nickname/deptName/isSuper/roles/perms/menus */
export const getProfile = () => request.get('/auth/me')

// ---------------------------------------------------------------------------
// 菜单与权限点（T-06）
// ---------------------------------------------------------------------------

/** 当前用户菜单树（侧边栏） */
export const myMenus = () => request.get('/menu/mine')

/** 全量菜单树（含按钮，用于角色权限分配） */
export const menuTree = () => request.get('/menu/tree')

// ---------------------------------------------------------------------------
// 部门（T-07）
// ---------------------------------------------------------------------------

export const deptTree = () => request.get('/dept/tree')

export const deptCreate = (data) => request.post('/dept', data)

export const deptUpdate = (id, data) => request.put(`/dept/${id}`, data)

export const deptDelete = (id) => request.delete(`/dept/${id}`)

// ---------------------------------------------------------------------------
// 用户（T-07）
// ---------------------------------------------------------------------------

/** 用户列表：{ keyword, deptId, enabled, page, size } → { items, total, page, size } */
export const userList = (params) => request.get('/user/list', { params })

export const userCreate = (data) => request.post('/user', data)

export const userUpdate = (id, data) => request.put(`/user/${id}`, data)

export const userDelete = (id) => request.delete(`/user/${id}`)

// ---------------------------------------------------------------------------
// 角色与权限分配（T-07 / T-08）
// ---------------------------------------------------------------------------

export const roleList = (params) => request.get('/role/list', { params })

export const roleCreate = (data) => request.post('/role', data)

export const roleUpdate = (id, data) => request.put(`/role/${id}`, data)

export const roleDelete = (id) => request.delete(`/role/${id}`)

/** 角色已分配的菜单/权限点 ID 数组 */
export const roleMenuIds = (id) => request.get(`/role/${id}/menus`)

/** 覆盖式分配角色权限：{ menuIds: number[] } */
export const roleAssignMenus = (id, data) => request.put(`/role/${id}/menus`, data)

// ---------------------------------------------------------------------------
// 知识管理（T-10 ~ T-17）
// export const knowledgeList = (params) => request.get('/knowledge/list', { params })
// export const supportedFormats = () => request.get('/knowledge/supported-formats')
// export const importStatus = (taskId) => request.get(`/knowledge/status/${taskId}`)
// export const assignDocPerms = (data) => request.post('/knowledge/perms/assign', data)
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// AI 问答（T-19 ~ T-26）
// export const chatQuery = (data) => request.post('/chat/query', data)
// export const chatSessions = () => request.get('/chat/sessions')
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// 知识沉淀（T-30 ~ T-34）
// export const faqList = (params) => request.get('/precipitation/faq/list', { params })
// export const gapList = (params) => request.get('/precipitation/gap/list', { params })
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// 运营看板（T-27 ~ T-29）
// export const dashOverview = (params) => request.get('/dashboard/overview', { params })
// ---------------------------------------------------------------------------

export { request }
