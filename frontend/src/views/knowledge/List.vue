<template>
  <div class="kb-page">
    <el-card shadow="never">
      <!-- 工具栏 -->
      <div class="kb-toolbar">
        <el-input
          v-model="query.keyword"
          placeholder="标题 / 文件名"
          style="width: 200px"
          clearable
          @keyup.enter="reload"
        />
        <el-select v-model="query.sourceType" placeholder="全部格式" clearable style="width: 140px">
          <el-option v-for="item in formats" :key="item.sourceType" :label="item.label" :value="item.sourceType" />
        </el-select>
        <el-select v-model="query.status" placeholder="全部状态" clearable style="width: 130px">
          <el-option label="处理中" value="pending" />
          <el-option label="可用" value="ready" />
          <el-option label="失败" value="failed" />
        </el-select>
        <el-button type="primary" @click="reload">查询</el-button>
        <el-button @click="onReset">重置</el-button>

        <div class="spacer" />

        <el-button v-permission="'knowledge:perm'" :disabled="!selection.length" @click="openPerm(null)">
          批量设权限（{{ selection.length }}）
        </el-button>
        <el-button v-permission="'knowledge:import'" type="success" @click="importDrawer = true">
          <el-icon><UploadFilled /></el-icon>导入文档
        </el-button>
      </div>

      <!-- 台账 -->
      <el-table v-loading="loading" :data="list" border stripe @selection-change="onSelectionChange">
        <el-table-column type="selection" width="46" />
        <el-table-column prop="title" label="知识单元" min-width="200" show-overflow-tooltip />
        <el-table-column label="格式" width="90">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ formatLabel(row.sourceType) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="分类" width="120">
          <template #default="{ row }">
            <span v-if="row.category">{{ row.category }}</span>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="数据权限" width="220">
          <template #default="{ row }">
            <el-tag v-if="row.permSummary.isGlobal" type="success" size="small">全局可见</el-tag>
            <template v-else-if="hasAnyPerm(row.permSummary)">
              <el-tag v-if="row.permSummary.deptIds.length" size="small" class="tag-gap">
                部门×{{ row.permSummary.deptIds.length }}
              </el-tag>
              <el-tag v-if="row.permSummary.roleIds.length" size="small" type="warning" class="tag-gap">
                角色×{{ row.permSummary.roleIds.length }}
              </el-tag>
              <el-tag v-if="row.permSummary.userIds.length" size="small" type="info" class="tag-gap">
                个人×{{ row.permSummary.userIds.length }}
              </el-tag>
            </template>
            <el-tag v-else type="danger" size="small" effect="plain">未分配</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="chunkCount" label="切片" width="80" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="更新时间" width="170">
          <template #default="{ row }">{{ formatTime(row.updatedAt) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button v-permission="'knowledge:perm'" link type="warning" @click="openPerm(row)">
              数据权限
            </el-button>
            <el-button v-permission="'knowledge:update'" link type="primary" @click="openEdit(row)">
              编辑
            </el-button>
            <el-button v-permission="'knowledge:delete'" link type="danger" @click="onDelete(row)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        class="pager"
        background
        layout="total, sizes, prev, pager, next"
        :total="total"
        :page-size="query.size"
        :current-page="query.page"
        :page-sizes="[10, 20, 50]"
        @current-change="onPageChange"
        @size-change="onSizeChange"
      />
    </el-card>

    <!-- 导入抽屉 -->
    <el-drawer v-model="importDrawer" title="导入知识文档" size="480px" @closed="onDrawerClosed">
      <el-upload
        drag
        multiple
        :show-file-list="false"
        :http-request="customUpload"
        :accept="acceptString"
      >
        <el-icon class="upload-icon"><UploadFilled /></el-icon>
        <div class="el-upload__text">将文件拖到此处，或 <em>点击选择</em></div>
        <template #tip>
          <div class="upload-tip">
            <div class="tip-label">支持格式：</div>
            <el-tag v-for="item in formats" :key="item.sourceType" size="small" effect="plain" class="tag-gap">
              {{ item.label }}
            </el-tag>
            <div class="tip-note">{{ maxUploadTip }}</div>
          </div>
        </template>
      </el-upload>

      <div v-if="progressList.length" class="progress-box">
        <div class="progress-title">处理进度</div>
        <div v-for="item in progressList" :key="item.taskId" class="progress-item">
          <div class="progress-head">
            <span class="progress-name">{{ item.filename }}</span>
            <el-tag :type="statusType(item.status)" size="small">{{ statusLabel(item.status) }}</el-tag>
          </div>
          <el-progress
            :percentage="stagePercent(item.stage)"
            :status="item.status === 'failed' ? 'exception' : item.status === 'done' ? 'success' : undefined"
            :stroke-width="8"
          />
          <div class="progress-stage">
            {{ stageLabel(item.stage) }}
            <span v-if="item.errorMsg" class="progress-error">{{ item.errorMsg }}</span>
          </div>
        </div>
      </div>
      <el-empty v-else description="尚未选择文件" :image-size="60" />
    </el-drawer>

    <!-- 数据权限 -->
    <el-dialog v-model="permDialog" title="数据权限分配" width="560px">
      <el-alert
        class="perm-target"
        type="info"
        :closable="false"
        show-icon
        :title="`配置对象：${permTarget.label}`"
      />
      <PermEntitySelector v-model="permValue" />
      <template #footer>
        <el-button @click="permDialog = false">取消</el-button>
        <el-button type="primary" :loading="permSaving" @click="savePerm">保存</el-button>
      </template>
    </el-dialog>

    <!-- 编辑 -->
    <el-dialog v-model="editDialog" title="编辑知识单元" width="480px">
      <el-form :model="editForm" label-width="80px">
        <el-form-item label="标题">
          <el-input v-model.trim="editForm.title" maxlength="255" />
        </el-form-item>
        <el-form-item label="分类">
          <el-input v-model.trim="editForm.category" maxlength="64" placeholder="如：财务制度" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="editForm.remark" type="textarea" :rows="2" maxlength="512" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="editForm.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialog = false">取消</el-button>
        <el-button type="primary" :loading="editSaving" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import {
  assignDocPerms,
  docPerms,
  importStatus,
  knowledgeDelete,
  knowledgeList,
  knowledgeUpdate,
  supportedFormats,
  uploadDocs,
} from '@/api'
import PermEntitySelector from '@/components/PermEntitySelector.vue'

const list = ref([])
const total = ref(0)
const loading = ref(false)
const selection = ref([])
const formats = ref([])

const importDrawer = ref(false)
const progressList = ref([])

const permDialog = ref(false)
const permSaving = ref(false)
const permTarget = reactive({ docIds: [], label: '' })
const permValue = ref({ isGlobal: false, deptIds: [], roleIds: [], userIds: [] })

const editDialog = ref(false)
const editSaving = ref(false)
const editForm = reactive({ docId: '', title: '', category: '', remark: '', enabled: true })

const query = reactive({ keyword: '', sourceType: '', status: '', page: 1, size: 10 })

const acceptString = computed(() =>
  formats.value.flatMap((item) => item.extensions).join(','),
)
const maxUploadTip = '单个文件不超过 50MB；图片类文档将由视觉模型生成内容描述后入库。'

const STAGE_LABELS = {
  pending: '排队等待',
  reading: '读取文件',
  parsing: '解析文档',
  images: '图片理解',
  splitting: '文本切片',
  embedding: '向量化入库',
  done: '处理完成',
  failed: '处理失败',
}
const STAGE_PERCENT = {
  pending: 10,
  reading: 25,
  parsing: 40,
  images: 55,
  splitting: 70,
  embedding: 85,
  done: 100,
  failed: 100,
}

function stageLabel(stage) {
  return STAGE_LABELS[stage] || stage || '等待中'
}
function stagePercent(stage) {
  return STAGE_PERCENT[stage] ?? 10
}
function formatLabel(sourceType) {
  return formats.value.find((item) => item.sourceType === sourceType)?.label || sourceType
}
function statusLabel(status) {
  return { pending: '处理中', ready: '可用', failed: '失败' }[status] || status
}
function statusType(status) {
  return { pending: 'warning', ready: 'success', failed: 'danger' }[status] || 'info'
}
function hasAnyPerm(summary) {
  return Boolean(summary?.deptIds?.length || summary?.roleIds?.length || summary?.userIds?.length)
}
function formatTime(value) {
  if (!value) return '—'
  return String(value).replace('T', ' ').slice(0, 16)
}

async function load() {
  loading.value = true
  try {
    const data = await knowledgeList({
      keyword: query.keyword || undefined,
      sourceType: query.sourceType || undefined,
      status: query.status || undefined,
      page: query.page,
      size: query.size,
    })
    list.value = data.items || []
    total.value = data.total || 0
  } finally {
    loading.value = false
  }
}

function reload() {
  query.page = 1
  load()
}
function onReset() {
  Object.assign(query, { keyword: '', sourceType: '', status: '', page: 1 })
  load()
}
function onPageChange(page) {
  query.page = page
  load()
}
function onSizeChange(size) {
  query.size = size
  query.page = 1
  load()
}
function onSelectionChange(rows) {
  selection.value = rows
}

// ---------------- 上传与进度 ----------------

async function customUpload(options) {
  const form = new FormData()
  form.append('files', options.file)
  try {
    const result = await uploadDocs(form)
    for (const item of result.accepted || []) {
      progressList.value.unshift({
        taskId: item.taskId,
        docId: item.docId,
        filename: item.filename,
        sourceType: item.sourceType,
        status: 'pending',
        stage: 'pending',
        errorMsg: '',
      })
    }
    for (const rejected of result.rejected || []) {
      ElMessage.error(`${rejected.filename}：${rejected.reason}`)
    }
    startPolling()
    options.onSuccess?.(result)
  } catch (error) {
    options.onError?.(error)
  }
}

let pollTimer = null

function startPolling() {
  if (pollTimer) return
  pollTimer = setInterval(async () => {
    const running = progressList.value.filter((item) => !['done', 'failed'].includes(item.status))
    if (!running.length) {
      stopPolling()
      return
    }

    let anyFinished = false
    for (const item of running) {
      try {
        const task = await importStatus(item.taskId)
        item.status = task.status
        item.stage = task.stage
        item.errorMsg = task.errorMsg || ''
        if (['done', 'failed'].includes(task.status)) anyFinished = true
      } catch {
        /* 单次查询失败不影响其他任务 */
      }
    }
    if (anyFinished) load()
  }, 2000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function onDrawerClosed() {
  // 抽屉关闭后停止轮询；已完成的进度保留，便于回看结果
  if (!progressList.value.some((item) => !['done', 'failed'].includes(item.status))) {
    stopPolling()
  }
}

// ---------------- 数据权限 ----------------

async function openPerm(row) {
  const docIds = row ? [row.docId] : selection.value.map((item) => item.docId)
  if (!docIds.length) {
    ElMessage.warning('请先选择要配置的知识单元')
    return
  }

  permTarget.docIds = docIds
  permTarget.label = row ? row.title : `已选 ${docIds.length} 个知识单元`

  if (docIds.length === 1) {
    try {
      permValue.value = await docPerms(docIds[0])
    } catch {
      permValue.value = { isGlobal: false, deptIds: [], roleIds: [], userIds: [] }
    }
  } else {
    // 批量配置以空白为起点：提交后所有目标单元的权限会被统一覆盖
    permValue.value = { isGlobal: false, deptIds: [], roleIds: [], userIds: [] }
  }
  permDialog.value = true
}

async function savePerm() {
  permSaving.value = true
  try {
    await assignDocPerms({ docIds: permTarget.docIds, ...permValue.value })
    ElMessage.success('数据权限已保存，立即生效')
    permDialog.value = false
    load()
  } catch {
    /* 错误提示由拦截器处理 */
  } finally {
    permSaving.value = false
  }
}

// ---------------- 编辑与删除 ----------------

function openEdit(row) {
  Object.assign(editForm, {
    docId: row.docId,
    title: row.title,
    category: row.category || '',
    remark: row.remark || '',
    enabled: row.enabled,
  })
  editDialog.value = true
}

async function saveEdit() {
  editSaving.value = true
  try {
    await knowledgeUpdate(editForm.docId, {
      title: editForm.title,
      category: editForm.category || null,
      remark: editForm.remark || null,
      enabled: editForm.enabled,
    })
    ElMessage.success('已保存')
    editDialog.value = false
    load()
  } catch {
    /* 错误提示由拦截器处理 */
  } finally {
    editSaving.value = false
  }
}

async function onDelete(row) {
  try {
    await ElMessageBox.confirm(
      `确认删除「${row.title}」？其切片与数据权限配置将一并清理。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }

  try {
    await knowledgeDelete(row.docId)
    ElMessage.success('已删除')
    load()
  } catch {
    /* 错误提示由拦截器处理 */
  }
}

onMounted(async () => {
  try {
    formats.value = await supportedFormats()
  } catch {
    formats.value = []
  }
  await load()
})

onUnmounted(stopPolling)
</script>

<style scoped>
.pager {
  margin-top: 12px;
  justify-content: flex-end;
}

.tag-gap {
  margin: 1px 4px 1px 0;
}

.muted {
  color: #c0c4cc;
}

.upload-icon {
  font-size: 48px;
  color: #c0c4cc;
  margin-top: 30px;
}

.upload-tip {
  margin-top: 8px;
  text-align: left;
}

.tip-label {
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
}

.tip-note {
  margin-top: 6px;
  font-size: 12px;
  color: #a8abb2;
  line-height: 1.6;
}

.progress-box {
  margin-top: 16px;
}

.progress-title {
  font-size: 13px;
  font-weight: 600;
  color: #606266;
  margin-bottom: 8px;
}

.progress-item {
  padding: 10px 12px;
  margin-bottom: 8px;
  background: #fafafa;
  border-radius: 6px;
}

.progress-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

.progress-name {
  font-size: 13px;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 300px;
}

.progress-stage {
  margin-top: 4px;
  font-size: 12px;
  color: #909399;
}

.progress-error {
  color: #f56c6c;
  margin-left: 6px;
}

.perm-target {
  margin-bottom: 12px;
}
</style>
