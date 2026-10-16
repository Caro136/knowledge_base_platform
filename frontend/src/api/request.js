/**
 * axios 实例与全局拦截。
 *
 * 约定（对应后端 SPEC §6.1）：
 *  - 后端统一返回 { code, message, data }，code === 0 表示成功；
 *  - 拦截器负责"解包"，业务代码拿到的直接就是 data；
 *  - 20001（未登录/凭证失效）统一跳转登录页；
 *  - 其余业务错误统一弹出 message，并抛出 BizError 供调用方按需处理。
 */

import axios from 'axios'
import { ElMessage } from 'element-plus'

import { clearToken, getToken } from '@/utils/auth'

/** 业务错误码 20001：未登录或登录状态已失效 */
const CODE_UNAUTHENTICATED = 20001

export class BizError extends Error {
  constructor(code, message, data) {
    super(message || '请求失败')
    this.name = 'BizError'
    this.code = code
    this.data = data
  }
}

const service = axios.create({
  // 开发环境走 Vite 代理，生产环境由后端同源托管，均使用相对路径
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  // 问答生成、文档导入均为长耗时操作
  timeout: 120000,
})

service.interceptors.request.use(
  (config) => {
    const token = getToken()
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error),
)

function redirectToLogin() {
  clearToken()
  const { pathname, search, hash } = window.location
  const current = `${pathname}${search}${hash}`
  if (!current.startsWith('/login')) {
    // 整页跳转：同时清空内存中的登录态，避免残留脏数据
    window.location.replace(`/login?redirect=${encodeURIComponent(current)}`)
  }
}

function toast(message) {
  if (message) {
    ElMessage.error(message)
  }
}

service.interceptors.response.use(
  (response) => {
    // 文件下载等二进制响应直接透传
    if (response.config.responseType === 'blob') {
      return response.data
    }

    const body = response.data
    // 非标准包装（第三方接口直传）原样返回
    if (!body || typeof body !== 'object' || !('code' in body)) {
      return body
    }

    if (body.code === 0) {
      return body.data
    }

    if (body.code === CODE_UNAUTHENTICATED) {
      redirectToLogin()
      return Promise.reject(new BizError(body.code, body.message))
    }

    toast(body.message)
    return Promise.reject(new BizError(body.code, body.message, body.data))
  },
  (error) => {
    const response = error.response

    if (!response) {
      // 无响应：超时或网络中断
      toast(error.code === 'ECONNABORTED' ? '请求超时，请稍后重试' : '网络异常，请检查后端服务是否可用')
      return Promise.reject(error)
    }

    const body = response.data
    const code = body?.code
    const message = body?.message

    if (response.status === 401 || code === CODE_UNAUTHENTICATED) {
      // 跳转前不弹提示，避免与登录页提示重叠
      redirectToLogin()
      return Promise.reject(new BizError(code ?? CODE_UNAUTHENTICATED, message || '登录状态已失效'))
    }

    toast(message || `请求失败（HTTP ${response.status}）`)
    return Promise.reject(new BizError(code ?? -1, message || `HTTP ${response.status}`, body))
  },
)

export default service
