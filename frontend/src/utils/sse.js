/**
 * SSE 客户端（T-26）。
 *
 * 为什么不用原生 EventSource：它无法携带自定义请求头，而问答接口要求
 * Authorization 头做登录态校验。因此改用 fetch + ReadableStream 手工解析。
 *
 * 事件格式（与后端 chat_service 约定）：
 *   event: stage|delta|references|notice|done|error
 *   data: {JSON}
 */

import { getToken } from '@/utils/auth'

/**
 * 连接 SSE 并逐事件回调。
 *
 * @param {string} path 相对路径，如 /api/chat/stream/xxx
 * @param {(event: {event: string, data: object}) => void} onEvent 事件回调
 * @param {AbortSignal} [signal] 用于中断生成
 */
export async function streamSse(path, onEvent, signal) {
  const response = await fetch(path, {
    headers: { Authorization: `Bearer ${getToken()}` },
    signal,
  })

  if (!response.ok) {
    // 非 2xx 时后端返回的是统一响应体，尽量把 message 透出
    let message = `SSE 连接失败（HTTP ${response.status}）`
    try {
      const body = await response.json()
      if (body?.message) message = body.message
    } catch {
      /* 保持默认文案 */
    }
    throw new Error(message)
  }
  if (!response.body) {
    throw new Error('当前浏览器不支持流式响应')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })

    // SSE 事件以空行分隔；最后一段可能不完整，留在缓冲区
    const chunks = buffer.split('\n\n')
    buffer = chunks.pop() || ''

    for (const chunk of chunks) {
      const event = parseChunk(chunk)
      if (event && onEvent) onEvent(event)
    }
  }
}

function parseChunk(chunk) {
  let eventName = 'message'
  const dataLines = []

  for (const line of chunk.split('\n')) {
    if (line.startsWith(':')) continue // 心跳/注释行
    if (line.startsWith('event:')) {
      eventName = line.slice(6).trim()
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trim())
    }
  }

  if (!dataLines.length) return null

  const raw = dataLines.join('\n')
  try {
    return { event: eventName, data: JSON.parse(raw) }
  } catch {
    return { event: eventName, data: { raw } }
  }
}
