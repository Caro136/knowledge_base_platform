<template>
  <div class="chat-layout">
    <!-- 左：会话 -->
    <aside class="chat-side">
      <el-button class="new-btn" type="primary" plain @click="newChat">
        <el-icon><Plus /></el-icon>新建对话
      </el-button>

      <div class="side-title">历史会话</div>
      <div class="session-list">
        <div
          v-for="item in sessions"
          :key="item.sessionId"
          :class="['session-item', { active: item.sessionId === sessionId }]"
          @click="openSession(item.sessionId)"
        >
          <el-icon class="session-icon"><ChatLineRound /></el-icon>
          <span class="session-title">{{ item.title || '新对话' }}</span>
          <el-icon class="session-del" @click.stop="removeSession(item)"><Delete /></el-icon>
        </div>
        <el-empty v-if="!sessions.length" description="暂无会话" :image-size="50" />
      </div>
    </aside>

    <!-- 右：对话 -->
    <section class="chat-main">
      <div class="chat-header">
        <span class="chat-title">{{ currentTitle }}</span>
        <el-button v-if="messages.length" link size="small" @click="clearCurrent">
          <el-icon><Delete /></el-icon>清空当前对话
        </el-button>
      </div>

      <div ref="msgBox" class="chat-messages" @scroll="onScroll">
        <div v-if="!messages.length" class="chat-welcome">
          <el-icon class="welcome-icon"><ChatDotRound /></el-icon>
          <div class="welcome-title">有什么可以帮您？</div>
          <div class="welcome-sub">基于已导入的企业知识作答，回答会标注来源；无权限的内容不会展示。</div>
        </div>

        <div v-for="(msg, index) in messages" :key="index" :class="['msg-row', msg.role]">
          <div :class="['avatar', msg.role]">
            <el-icon v-if="msg.role === 'assistant'"><Avatar /></el-icon>
            <el-icon v-else><UserFilled /></el-icon>
          </div>

          <div class="bubble-wrap">
            <!-- 权限受限等安全提示 -->
            <el-alert
              v-if="msg.notice"
              class="notice"
              :type="msg.notice.type === 'permission_denied' ? 'warning' : 'info'"
              :title="msg.notice.message"
              :closable="false"
              show-icon
            />

            <div class="bubble">
              <div v-if="msg.streaming && !msg.text" class="thinking">
                <span class="dot-flash">●</span>
                {{ msg.stage || '思考中…' }}
              </div>
              <div v-else class="md-body" v-html="renderMarkdown(msg.text)"></div>

              <!-- 引用溯源 -->
              <div v-if="msg.references?.length" class="refs">
                <div class="refs-title">
                  <el-icon><Link /></el-icon>引用来源（{{ msg.references.length }}）
                </div>
                <div v-for="ref in msg.references" :key="ref.index" class="ref-item">
                  <span class="ref-index">[{{ ref.index }}]</span>
                  <span class="ref-title">{{ ref.title }}</span>
                  <el-tooltip placement="top" :show-after="200">
                    <template #content>
                      <div class="ref-tooltip">
                        <div class="ref-tooltip-title">{{ ref.parentTitle || ref.fileTitle || ref.title }}</div>
                        <div class="ref-tooltip-body">{{ ref.snippet }}</div>
                      </div>
                    </template>
                    <el-icon class="ref-info"><InfoFilled /></el-icon>
                  </el-tooltip>
                </div>
              </div>
            </div>

            <div v-if="!msg.streaming && msg.text" class="msg-actions">
              <el-tooltip content="复制回答" placement="top">
                <el-icon class="act" @click="copyText(msg.text)"><CopyDocument /></el-icon>
              </el-tooltip>
            </div>
          </div>
        </div>
      </div>

      <transition name="fade">
        <div v-if="!autoFollow" class="to-bottom" @click="scrollToBottom">
          <el-icon><ArrowDown /></el-icon>
          <span v-if="sending" class="to-bottom-text">正在生成</span>
        </div>
      </transition>

      <div class="chat-input">
        <el-input
          v-model="input"
          type="textarea"
          :autosize="{ minRows: 1, maxRows: 5 }"
          resize="none"
          maxlength="1000"
          show-word-limit
          placeholder="输入问题，Enter 发送，Shift + Enter 换行"
          @keydown.enter.exact.prevent="send"
        />
        <div class="input-side">
          <el-button v-if="sending" type="danger" plain @click="stop">
            <el-icon><VideoPause /></el-icon>停止
          </el-button>
          <el-button v-else type="primary" :disabled="!input.trim()" @click="send">
            <el-icon><Promotion /></el-icon>发送
          </el-button>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
/**
 * AI 智能问答工作台（T-26）。
 *
 * 交互要点：
 * - SSE 流式接收（stage / delta / references / notice / done / error）；
 * - 权限受限时后端不生成正文，前端只展示安全提示条；
 * - 引用来源以折叠列表呈现，悬浮可看切片摘录。
 */
import { computed, nextTick, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { chatDeleteSession, chatHistory, chatQuery, chatSessions } from '@/api'
import { renderMarkdown } from '@/utils/markdown'
import { streamSse } from '@/utils/sse'

const messages = ref([])
const sessions = ref([])
const sessionId = ref('')
const input = ref('')
const sending = ref(false)
const msgBox = ref(null)

let controller = null
let autoFollow = true

const currentTitle = computed(() => {
  const first = messages.value.find((item) => item.role === 'user')
  return first ? first.text.slice(0, 30) : '新对话'
})

// ---------------- 会话 ----------------

async function loadSessions() {
  try {
    sessions.value = await chatSessions()
  } catch {
    sessions.value = []
  }
}

function newChat() {
  sessionId.value = ''
  messages.value = []
  input.value = ''
}

async function openSession(id) {
  if (sending.value) {
    ElMessage.warning('正在生成回答，请先停止或等待完成')
    return
  }
  try {
    const history = await chatHistory(id)
    sessionId.value = id
    messages.value = history.map((item) => ({
      role: item.role,
      text: item.content || '',
      references: item.references || [],
      notice: null,
      streaming: false,
      stage: '',
    }))
    await nextTick()
    scrollToBottom(true)
  } catch {
    /* 错误提示由拦截器处理 */
  }
}

async function removeSession(item) {
  try {
    await ElMessageBox.confirm(`确认删除会话「${item.title}」？`, '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    await chatDeleteSession(item.sessionId)
    if (item.sessionId === sessionId.value) newChat()
    await loadSessions()
    ElMessage.success('会话已删除')
  } catch {
    /* 错误提示由拦截器处理 */
  }
}

function clearCurrent() {
  if (sending.value) {
    ElMessage.warning('正在生成回答，请先停止')
    return
  }
  messages.value = []
  sessionId.value = ''
}

// ---------------- 问答 ----------------

async function send() {
  const question = input.value.trim()
  if (!question || sending.value) return

  input.value = ''
  messages.value.push({ role: 'user', text: question, references: [], notice: null, streaming: false })

  const assistant = {
    role: 'assistant',
    text: '',
    references: [],
    notice: null,
    streaming: true,
    stage: '',
  }
  messages.value.push(assistant)
  sending.value = true
  await scrollToBottom(true)

  try {
    const result = await chatQuery({
      question,
      sessionId: sessionId.value || undefined,
    })
    sessionId.value = result.sessionId
    await streamAnswer(result.taskId, assistant)
    await loadSessions()
  } catch (error) {
    assistant.text = assistant.text || `请求失败：${error?.message || error}`
  } finally {
    assistant.streaming = false
    sending.value = false
    controller = null
  }
}

async function streamAnswer(taskId, assistant) {
  controller = new AbortController()

  await streamSse(
    `/api/chat/stream/${taskId}`,
    (event) => {
      switch (event.event) {
        case 'stage':
          assistant.stage = event.data.label || ''
          break
        case 'delta':
          assistant.text += event.data.text || ''
          break
        case 'references':
          assistant.references = event.data.items || []
          break
        case 'notice':
          assistant.notice = event.data
          break
        case 'done':
          // 以最终答案为准确认值，避免增量拼接与服务端结果不一致
          assistant.text = event.data.answer || assistant.text
          assistant.references = event.data.references || assistant.references
          assistant.stage = ''
          break
        case 'error':
          assistant.text = assistant.text || event.data.message || '生成失败'
          ElMessage.error(event.data.message || '生成失败')
          break
        default:
          break
      }
      scrollToBottom()
    },
    controller.signal,
  )
}

function stop() {
  controller?.abort()
  controller = null
  sending.value = false
  const last = messages.value[messages.value.length - 1]
  if (last && last.role === 'assistant') last.streaming = false
}

// ---------------- 视图辅助 ----------------

function onScroll() {
  const el = msgBox.value
  if (!el) return
  // 距底部 60px 内视为「贴底」，恢复自动跟随；用户上翻时暂停
  autoFollow = el.scrollHeight - el.scrollTop - el.clientHeight < 60
}

async function scrollToBottom(force = false) {
  if (!force && !autoFollow) return
  await nextTick()
  const el = msgBox.value
  if (el) {
    el.scrollTop = el.scrollHeight
    autoFollow = true
  }
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制')
  } catch {
    ElMessage.warning('当前环境不支持自动复制')
  }
}

onMounted(loadSessions)
</script>

<style scoped>
.chat-layout {
  display: flex;
  height: calc(100vh - var(--kb-header-height));
  background: #fff;
}

.chat-side {
  display: flex;
  flex-direction: column;
  width: 240px;
  border-right: 1px solid var(--kb-border);
  padding: 12px;
}

.new-btn {
  width: 100%;
  margin-bottom: 12px;
}

.side-title {
  font-size: 12px;
  color: #909399;
  margin: 4px 0 8px;
}

.session-list {
  flex: 1;
  overflow: auto;
}

.session-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  color: #303133;
}

.session-item:hover {
  background: #f5f7fa;
}

.session-item.active {
  background: #ecf5ff;
  color: #409eff;
}

.session-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-del {
  opacity: 0;
  color: #f56c6c;
}

.session-item:hover .session-del {
  opacity: 1;
}

.chat-main {
  position: relative; /* 「回到底部」浮层需要定位锚点 */
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
}

.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 44px;
  padding: 0 16px;
  border-bottom: 1px solid var(--kb-border);
}

.chat-title {
  font-size: 14px;
  font-weight: 600;
}

.chat-messages {
  flex: 1;
  overflow: auto;
  padding: 16px 24px;
}

.chat-welcome {
  text-align: center;
  padding-top: 60px;
  color: #909399;
}

.welcome-icon {
  font-size: 48px;
  color: #c0c4cc;
}

.welcome-title {
  margin-top: 12px;
  font-size: 16px;
  color: #303133;
}

.welcome-sub {
  margin-top: 6px;
  font-size: 13px;
}

.msg-row {
  display: flex;
  gap: 10px;
  margin-bottom: 18px;
}

.msg-row.user {
  flex-direction: row-reverse;
}

.avatar {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  flex-shrink: 0;
  color: #fff;
}

.avatar.assistant {
  background: #409eff;
}

.avatar.user {
  background: #67c23a;
}

.bubble-wrap {
  max-width: 78%;
  min-width: 0;
}

.notice {
  margin-bottom: 8px;
}

.bubble {
  padding: 10px 14px;
  border-radius: 8px;
  background: #f5f7fa;
  font-size: 14px;
  line-height: 1.75;
  word-break: break-word;
}

.msg-row.user .bubble {
  background: #ecf5ff;
}

.md-body :deep(p) {
  margin: 6px 0;
}

.md-body :deep(pre) {
  background: #f6f8fa;
  padding: 10px;
  border-radius: 6px;
  overflow: auto;
}

.md-body :deep(table) {
  border-collapse: collapse;
  margin: 8px 0;
}

.md-body :deep(th),
.md-body :deep(td) {
  border: 1px solid #dcdfe6;
  padding: 4px 8px;
}

.thinking {
  color: #909399;
}

.dot-flash {
  animation: flash 1s infinite;
  margin-right: 4px;
}

@keyframes flash {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.2; }
}

.refs {
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px dashed #dcdfe6;
}

.refs-title {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #909399;
  margin-bottom: 6px;
}

.ref-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #606266;
  padding: 2px 0;
}

.ref-index {
  color: #409eff;
  font-weight: 600;
}

.ref-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 420px;
}

.ref-info {
  color: #c0c4cc;
  cursor: help;
}

.ref-tooltip {
  max-width: 380px;
}

.ref-tooltip-title {
  font-weight: 600;
  margin-bottom: 4px;
}

.ref-tooltip-body {
  font-size: 12px;
  line-height: 1.6;
  color: #e5eaf3;
}

.msg-actions {
  margin-top: 4px;
}

.act {
  cursor: pointer;
  color: #c0c4cc;
}

.act:hover {
  color: #409eff;
}

.to-bottom {
  position: absolute;
  right: 40px;
  bottom: 110px;
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  background: #fff;
  border: 1px solid var(--kb-border);
  border-radius: 16px;
  cursor: pointer;
  font-size: 12px;
  color: #606266;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.chat-input {
  display: flex;
  gap: 10px;
  padding: 12px 16px;
  border-top: 1px solid var(--kb-border);
}

.chat-input :deep(.el-textarea) {
  flex: 1;
}

.input-side {
  display: flex;
  align-items: flex-end;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
