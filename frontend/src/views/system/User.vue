<template>
  <div class="kb-page">
    <el-card shadow="never">
      <!-- 工具栏 -->
      <div class="kb-toolbar">
        <el-input
          v-model="query.keyword"
          placeholder="账号 / 昵称"
          style="width: 200px"
          clearable
          @keyup.enter="reload"
        />
        <el-tree-select
          v-model="query.deptId"
          :data="deptOptions"
          node-key="id"
          :props="{ label: 'name', children: 'children' }"
          :render-after-expand="false"
          check-strictly
          clearable
          placeholder="全部部门"
          style="width: 190px"
        />
        <el-select v-model="query.enabled" placeholder="全部状态" clearable style="width: 130px">
          <el-option label="启用" :value="true" />
          <el-option label="停用" :value="false" />
        </el-select>
        <el-button type="primary" @click="reload">查询</el-button>
        <el-button @click="onReset">重置</el-button>

        <div class="spacer" />

        <el-button v-permission="'user:create'" type="success" @click="openCreate">
          <el-icon><Plus /></el-icon>新增用户
        </el-button>
      </div>

      <!-- 列表 -->
      <el-table v-loading="loading" :data="list" border stripe>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="username" label="账号" min-width="130" />
        <el-table-column prop="nickname" label="昵称" min-width="120" />
        <el-table-column prop="deptName" label="所属部门" min-width="130">
          <template #default="{ row }">
            <span v-if="row.deptName">{{ row.deptName }}</span>
            <span v-else class="muted">未分配</span>
          </template>
        </el-table-column>
        <el-table-column label="角色" min-width="200">
          <template #default="{ row }">
            <el-tag v-if="row.isSuper" type="danger" size="small">超级管理员</el-tag>
            <template v-else>
              <el-tag
                v-for="name in row.roleNames"
                :key="name"
                size="small"
                type="warning"
                effect="plain"
                class="role-tag"
              >
                {{ name }}
              </el-tag>
              <span v-if="!row.roleNames?.length" class="muted">未分配</span>
            </template>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.enabled ? 'success' : 'info'" size="small">
              {{ row.enabled ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="createdAt" label="创建时间" width="170" />
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button v-permission="'user:update'" link type="primary" @click="openEdit(row)">
              编辑
            </el-button>
            <el-button
              v-permission="'user:delete'"
              link
              type="danger"
              :disabled="row.isSuper"
              @click="onDelete(row)"
            >
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

    <!-- 新增 / 编辑 -->
    <el-dialog v-model="dialog" :title="form.id ? '编辑用户' : '新增用户'" width="520px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="账号" prop="username">
          <el-input v-model.trim="form.username" maxlength="64" placeholder="字母、数字、下划线、点、横线" />
        </el-form-item>
        <el-form-item label="密码" :prop="form.id ? '' : 'password'">
          <el-input
            v-model="form.password"
            type="password"
            show-password
            :placeholder="form.id ? '留空表示不修改密码' : '至少 6 位'"
          />
        </el-form-item>
        <el-form-item label="昵称">
          <el-input v-model.trim="form.nickname" maxlength="64" />
        </el-form-item>
        <el-form-item label="所属部门">
          <el-tree-select
            v-model="form.deptId"
            :data="deptOptions"
            node-key="id"
            :props="{ label: 'name', children: 'children' }"
            :render-after-expand="false"
            check-strictly
            clearable
            placeholder="可不分配"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="form.roleIds" multiple clearable placeholder="可多选" style="width: 100%">
            <el-option
              v-for="role in roles"
              :key="role.id"
              :label="role.name"
              :value="role.id"
              :disabled="!role.enabled"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="form.enabled" active-text="启用" inactive-text="停用" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSubmit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { deptTree, roleList, userCreate, userDelete, userList, userUpdate } from '@/api'

const list = ref([])
const total = ref(0)
const loading = ref(false)

const deptOptions = ref([])
const roles = ref([])

const dialog = ref(false)
const saving = ref(false)
const formRef = ref(null)

const query = reactive({
  keyword: '',
  deptId: null,
  enabled: null,
  page: 1,
  size: 10,
})

const form = reactive({
  id: null,
  username: '',
  password: '',
  nickname: '',
  deptId: null,
  roleIds: [],
  enabled: true,
})

const rules = {
  username: [
    { required: true, message: '请输入账号', trigger: 'blur' },
    {
      pattern: /^[A-Za-z0-9_.-]+$/,
      message: '账号仅允许字母、数字、下划线、点与横线',
      trigger: 'blur',
    },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码至少 6 位', trigger: 'blur' },
  ],
}

async function load() {
  loading.value = true
  try {
    const data = await userList({
      keyword: query.keyword || undefined,
      deptId: query.deptId || undefined,
      enabled: query.enabled === null ? undefined : query.enabled,
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
  Object.assign(query, { keyword: '', deptId: null, enabled: null, page: 1 })
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

/** 部门树与角色列表是下拉选项，部门树失败不阻断页面（可能无 dept:list 权限） */
async function loadOptions() {
  try {
    deptOptions.value = await deptTree()
  } catch {
    deptOptions.value = []
  }
  try {
    roles.value = await roleList()
  } catch {
    roles.value = []
  }
}

function openCreate() {
  Object.assign(form, {
    id: null,
    username: '',
    password: '',
    nickname: '',
    deptId: null,
    roleIds: [],
    enabled: true,
  })
  dialog.value = true
}

function openEdit(row) {
  Object.assign(form, {
    id: row.id,
    username: row.username,
    password: '',
    nickname: row.nickname || '',
    deptId: row.deptId,
    roleIds: [...(row.roleIds || [])],
    enabled: row.enabled,
  })
  dialog.value = true
}

async function onSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  const payload = {
    username: form.username,
    nickname: form.nickname || null,
    deptId: form.deptId || null,
    roleIds: form.roleIds,
    enabled: form.enabled,
  }
  // 编辑时留空表示不修改密码；后端字段带 min_length 校验，因此为空时必须不传该字段
  if (form.password) {
    payload.password = form.password
  }

  saving.value = true
  try {
    if (form.id) {
      await userUpdate(form.id, payload)
      ElMessage.success('用户已更新')
    } else {
      await userCreate(payload)
      ElMessage.success('用户已创建')
    }
    dialog.value = false
    await load()
  } catch {
    // 错误提示由 axios 拦截器统一处理
  } finally {
    saving.value = false
  }
}

async function onDelete(row) {
  try {
    await ElMessageBox.confirm(`确认删除用户「${row.nickname || row.username}」？`, '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return // 用户取消
  }

  try {
    await userDelete(row.id)
    ElMessage.success('用户已删除')
    await load()
  } catch {
    // 错误提示由拦截器处理
  }
}

onMounted(async () => {
  await Promise.all([load(), loadOptions()])
})
</script>

<style scoped>
.pager {
  margin-top: 12px;
  justify-content: flex-end;
}

.role-tag {
  margin: 2px 4px 2px 0;
}

.muted {
  color: #c0c4cc;
}
</style>
