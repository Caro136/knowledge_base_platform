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
// ---------------------------------------------------------------------------

/** 知识单元台账：{ keyword, sourceType, category, status, enabled, page, size } */
export const knowledgeList = (params) => request.get('/knowledge/list', { params })

export const knowledgeDetail = (docId) => request.get(`/knowledge/${docId}`)

export const knowledgeUpdate = (docId, data) => request.put(`/knowledge/${docId}`, data)

export const knowledgeDelete = (docId) => request.delete(`/knowledge/${docId}`)

/** 支持的 7 类文档格式与扩展名 */
export const supportedFormats = () => request.get('/knowledge/supported-formats')

/** 导入任务进度（前端轮询） */
export const importStatus = (taskId) => request.get(`/knowledge/status/${taskId}`)

/** 批量上传：FormData（字段名 files） */
export const uploadDocs = (formData, onUploadProgress) =>
  request.post('/knowledge/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress,
    timeout: 300000,
  })

/** 查询知识单元的四维数据权限 */
export const docPerms = (docId) => request.get(`/knowledge/${docId}/perms`)

/** 覆盖式分配四维数据权限：{ docIds, isGlobal, deptIds, roleIds, userIds } */
export const assignDocPerms = (data) => request.post('/knowledge/perms/assign', data)

/** 知识单元图片资源地址（供 <img> 直接引用） */
export const docAssetUrl = (docId, name) => `/api/knowledge/${docId}/assets/${encodeURIComponent(name)}`

// ---------------------------------------------------------------------------
// AI 问答（T-19 ~ T-26）
// ---------------------------------------------------------------------------

/** 发起问答 → { taskId, sessionId }；正文经 SSE 推送（见 utils/sse.js） */
export const chatQuery = (data) => request.post('/chat/query', data)

export const chatSessions = () => request.get('/chat/sessions')

export const chatHistory = (sessionId) => request.get(`/chat/history/${sessionId}`)

export const chatDeleteSession = (sessionId) => request.delete(`/chat/history/${sessionId}`)

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
