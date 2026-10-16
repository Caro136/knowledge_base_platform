/**
 * 接口定义。
 *
 * 按后端模块分组，函数名与 SPEC §6.2 的接口清单一一对应；
 * 未实现的模块在对应任务中补充（见注释中的任务号）。
 */

import request from './request'

// ---------------------------------------------------------------------------
// 认证与当前用户（T-05）
// ---------------------------------------------------------------------------

/** 登录：{ username, password } → { token, expiresIn, userInfo } */
export const login = (data) => request.post('/auth/login', data)

/** 登出（无状态 JWT，仅作语义标记） */
export const logout = () => request.post('/auth/logout')

/** 当前用户：userInfo 含 id/username/nickname/deptName/isSuper/perms/menus */
export const getProfile = () => request.get('/auth/me')

// ---------------------------------------------------------------------------
// 组织与权限（T-06 ~ T-08）
// export const deptTree = () => request.get('/dept/tree')
// export const userList = (params) => request.get('/user/list', { params })
// export const roleList = (params) => request.get('/role/list', { params })
// export const menuTree = () => request.get('/menu/tree')
// ---------------------------------------------------------------------------

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
// export const chatHistory = (sessionId) => request.get(`/chat/history/${sessionId}`)
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// 知识沉淀（T-30 ~ T-34）
// export const faqList = (params) => request.get('/precipitation/faq/list', { params })
// export const faqAudit = (id, data) => request.put(`/precipitation/faq/${id}/audit`, data)
// export const gapList = (params) => request.get('/precipitation/gap/list', { params })
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// 运营看板（T-27 ~ T-29）
// export const dashOverview = (params) => request.get('/dashboard/overview', { params })
// export const dashTrend = (params) => request.get('/dashboard/trend', { params })
// export const dashTopQuestions = (params) => request.get('/dashboard/top-questions', { params })
// export const dashTopDocs = (params) => request.get('/dashboard/top-docs', { params })
// ---------------------------------------------------------------------------

export { request }
