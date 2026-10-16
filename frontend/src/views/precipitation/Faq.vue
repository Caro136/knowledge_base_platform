<template>
  <div class="kb-page">
    <el-card shadow="never">
      <div class="kb-toolbar">
        <el-radio-group v-model="query.status" @change="reload">
          <el-radio-button label="">全部</el-radio-button>
          <el-radio-button label="pending">待审核</el-radio-button>
          <el-radio-button label="published">已发布</el-radio-button>
          <el-radio-button label="rejected">已驳回</el-radio-button>
        </el-radio-group>
        <el-input
          v-model="query.keyword"
          placeholder="问题 / 答案"
          style="width: 220px"
          clearable
          @keyup.enter="reload"
        />
        <el-button type="primary" @click="reload">查询</el-button>
      </div>

      <el-alert
        class="tip"
        type="info"
        :closable="false"
        show-icon
        title="系统按问题指纹聚合历史提问，同一问题达到阈值后自动进入「待审核」；发布后该问题将直接命中缓存作答，不再走检索与生成。"
      />

      <el-table v-loading="loading" :data="list" border stripe>
        <el-table-column prop="question" label="问题" min-width="240" show-overflow-tooltip />
        <el-table-column prop="hitCount" label="命中次数" width="100" sortable />
        <el-table-column label="来源" width="100">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ row.source === 'auto' ? '自动推荐' : '手工' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="置信度" width="90">
          <template #default="{ row }">
            <span v-if="row.confidence != null">{{ row.confidence }}</span>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="时间" width="170">
          <template #default="{ row }">{{ formatTime(row.publishedAt || row.createdAt) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button v-permission="'faq:audit'" link type="success" @click="openAudit(row)">
              {{ row.status === 'published' ? '修订答案' : '审核' }}
            </el-button>
            <el-button v-permission="'faq:audit'" link type="warning" @click="openPerm(row)">
              数据权限
            </el-button>
            <el-button v-permission="'faq:delete'" link type="danger" @click="onDelete(row)">
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

    <!-- 审核 -->
    <el-dialog v-model="auditDialog" title="FAQ 审核" width="560px">
      <el-form label-width="70px">
        <el-form-item label="问题">
          <div class="question-text">{{ current?.question }}</div>
        </el-form-item>
        <el-form-item label="频次">
          <el-tag size="small" type="warning">累计命中 {{ current?.hitCount }} 次</el-tag>
        </el-form-item>
        <el-form-item label="答案">
          <el-input
            v-model="answer"
            type="textarea"
            :rows="7"
            maxlength="4000"
            show-word-limit
            placeholder="确认或修订标准答案；发布后该问题将直接返回此答案"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="auditDialog = false">取消</el-button>
        <el-button type="danger" plain :loading="saving" @click="doAudit('reject')">驳回</el-button>
        <el-button type="success" :loading="saving" @click="doAudit('publish')">发布上线</el-button>
      </template>
    </el-dialog>

    <!-- 数据权限 -->
    <el-dialog v-model="permDialog" title="FAQ 数据权限" width="560px">
      <PermEntitySelector
        v-model="permValue"
        tip="FAQ 的默认语义与知识单元不同：不设置任何权限 = 所有人可见；一旦设置了权限，则仅命中的部门/角色/个人可用（命中缓存同样受此约束）。"
      />
      <template #footer>
        <el-button @click="permDialog = false">取消</el-button>
        <el-button type="primary" :loading="permSaving" @click="savePerm">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
/** FAQ 挖掘与审核发布（T-34）。 */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { assignFaqPerms, faqAudit, faqDelete, faqList, faqPerms } from '@/api'
import PermEntitySelector from '@/components/PermEntitySelector.vue'

const list = ref([])
const total = ref(0)
const loading = ref(false)

const query = reactive({ status: '', keyword: '', page: 1, size: 10 })

const auditDialog = ref(false)
const saving = ref(false)
const current = ref(null)
const answer = ref('')

const permDialog = ref(false)
const permSaving = ref(false)
const permValue = ref({ isGlobal: false, deptIds: [], roleIds: [], userIds: [] })

function statusLabel(status) {
  return { pending: '待审核', published: '已发布', rejected: '已驳回', collecting: '收集中' }[status] || status
}
function statusType(status) {
  return { pending: 'warning', published: 'success', rejected: 'info', collecting: 'info' }[status] || 'info'
}
function formatTime(value) {
  if (!value) return '—'
  return String(value).replace('T', ' ').slice(0, 16)
}

async function load() {
  loading.value = true
  try {
    const data = await faqList({
      keyword: query.keyword || undefined,
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
function onPageChange(page) {
  query.page = page
  load()
}
function onSizeChange(size) {
  query.size = size
  query.page = 1
  load()
}

function openAudit(row) {
  current.value = row
  answer.value = row.answer || ''
  auditDialog.value = true
}

async function doAudit(action) {
  if (action === 'publish' && !answer.value.trim()) {
    ElMessage.warning('发布前请填写标准答案')
    return
  }
  saving.value = true
  try {
    await faqAudit(current.value.id, { action, answer: answer.value || null })
    ElMessage.success(action === 'publish' ? '已发布，后续相同提问将命中缓存' : '已驳回')
    auditDialog.value = false
    load()
  } catch {
    /* 错误提示由拦截器处理 */
  } finally {
    saving.value = false
  }
}

async function openPerm(row) {
  current.value = row
  try {
    permValue.value = await faqPerms(row.id)
  } catch {
    permValue.value = { isGlobal: false, deptIds: [], roleIds: [], userIds: [] }
  }
  permDialog.value = true
}

async function savePerm() {
  permSaving.value = true
  try {
    await assignFaqPerms({ docIds: [String(current.value.id)], ...permValue.value })
    ElMessage.success('权限已保存')
    permDialog.value = false
  } catch {
    /* 错误提示由拦截器处理 */
  } finally {
    permSaving.value = false
  }
}

async function onDelete(row) {
  try {
    await ElMessageBox.confirm(
      `确认删除该 FAQ？删除后该问题将不再命中缓存。\n「${row.question}」`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    await faqDelete(row.id)
    ElMessage.success('已删除')
    load()
  } catch {
    /* 错误提示由拦截器处理 */
  }
}

onMounted(load)
</script>

<style scoped>
.tip {
  margin-bottom: 12px;
}
.pager {
  margin-top: 12px;
  justify-content: flex-end;
}
.muted {
  color: #c0c4cc;
}
.question-text {
  line-height: 1.6;
  color: #303133;
}
</style>
