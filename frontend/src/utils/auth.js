/**
 * 登录凭证的本地存取。
 *
 * 单独成模块（而非放在 Pinia store 中）的原因：
 * axios 拦截器与路由守卫都要读写 token，若直接依赖 store，
 * 会造成 request → store → api → request 的循环引用。
 */

const TOKEN_KEY = 'kb_token'

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY) || ''
  } catch {
    // 隐私模式等场景下 localStorage 不可用，降级为未登录
    return ''
  }
}

export function setToken(token) {
  try {
    localStorage.setItem(TOKEN_KEY, token)
  } catch {
    /* 忽略写入失败 */
  }
}

export function clearToken() {
  try {
    localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* 忽略删除失败 */
  }
}
