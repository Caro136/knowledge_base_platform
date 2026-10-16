<template>
  <div class="kb-page">
    <el-card shadow="never">
      <el-alert
        class="tip"
        type="warning"
        :closable="false"
        show-icon
        title="知识缺口：用户提问但知识库中没有可用于作答的内容。已排除「表述不清未真正检索」与「内容存在但无权限」两类情形。"
      />

      <div class="kb-toolbar">
        <el-checkbox v-model="query.includeResolved" @change="reload">显示已处理</el-checkbox>
        <el-button type="primary" @click="reload">刷新</el-button>
      </div>

      <el-table v-loading="loading" :data="list" border stripe>
        <el-table-column prop="question" label="未命中的问题" min-width="260" show-overflow-tooltip />
        <el-table-column prop="hitCount" label="出现次数" width="110" sortable />
        <el-table-column label="提问部门" width="140">
          <template #default="{ row }">
            <span v-if="row.deptName">{{ row.deptName }}</span>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.resolved ? 'success' : 'warning'" size="small">
              {{ row.resolved ? '已处理' : '待处理' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="首次出现" width="170">
          <template #default="{ row }">{{ formatTime(row.createdAt) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button v-permission="'gap:handle'" link type="primary" :disabled="row.resolved" @click="openTask(row)">
              转建补充任务
            </el-button>
            <el-button v-permission="'gap:handle'" link type="success" :disabled="row.resolved" @click="onResolve(row)">
              标记已解决
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

    <!-- 转建补充任务 -->
    <el-dialog v-model="taskDialog" title="转建知识补充任务" width="520px">
      <el-alert
        class="target"
        type="info"
        :closable="false"
        show-icon
        :title="`来源缺口：${current?.question || ''}`"
      />
      <el-form label-width="80px">
        <el-form-item label="任务标题">
          <el-input v-model.trim="taskForm.title" maxlength="255" placeholder="留空则按缺口问题自动生成" />
        </el-form-item>
        <el-form-item label="负责人">
          <el-select v-model="taskForm.ownerId" filterable clearable placeholder="默认为当前账号" style="width: 100%">
            <el-option
              v-for="user in userOptions"
              :key="user.id"
              :label="`${user.nickname || user.username}（${user.username}）`"
              :value="user.id"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="taskDialog = false">取消</el-button>
        <el-button type="primary" :loading="taskSaving" @click="saveTask">创建任务</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
/** 知识缺口清单与转建补充任务（T-34）。 */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { gapCreateTask, gapList, gapResolve, userList } from '@/api'

const list = ref([])
const total = ref(0)
const loading = ref(false)
const userOptions = ref([])

const query = reactive({ includeResolved: false, page: 1, size: 10 })

const taskDialog = ref(false)
const taskSaving = ref(false)
const current = ref(null)
const taskForm = reactive({ title: '', ownerId: null })

function formatTime(value) {
  if (!value) return '—'
  return String(value).replace('T', ' ').slice(0, 16)
}

async function load() {
  loading.value = true
  try {
    const data = await gapList({
      includeResolved: query.includeResolved,
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

function openTask(row) {
  current.value = row
  Object.assign(taskForm, { title: '', ownerId: null })
  taskDialog.value = true
}

async function saveTask() {
  taskSaving.value = true
  try {
    const task = await gapCreateTask(current.value.id, {
      title: taskForm.title || null,
      ownerId: taskForm.ownerId || null,
    })
    ElMessage.success(`已创建任务：${task.title}`)
    taskDialog.value = false
    load()
  } catch {
    /* 错误提示由拦截器处理 */
  } finally {
    taskSaving.value = false
  }
}

async function onResolve(row) {
  try {
    await ElMessageBox.confirm(`确认将「${row.question}」标记为已解决？`, '确认', {
      type: 'warning',
      confirmButtonText: '标记解决',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    await gapResolve(row.id)
    ElMessage.success('已标记解决')
    load()
  } catch {
    /* 错误提示由拦截器处理 */
  }
}

onMounted(async () => {
  await load()
  try {
    const page = await userList({ page: 1, size: 100 })
    userOptions.value = page?.items || []
  } catch {
    userOptions.value = []
  }
})
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
.target {
  margin-bottom: 12px;
}
</style>
