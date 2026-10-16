<template>
  <div class="kb-page">
    <el-card shadow="never">
      <div class="kb-toolbar">
        <el-input
          v-model="keyword"
          placeholder="角色名称 / 编码"
          style="width: 220px"
          clearable
          @keyup.enter="load"
        />
        <el-button type="primary" @click="load">查询</el-button>
        <div class="spacer" />
        <el-button v-permission="'role:create'" type="success" @click="openCreate">
          <el-icon><Plus /></el-icon>新增角色
        </el-button>
      </div>

      <el-table v-loading="loading" :data="list" border stripe>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="name" label="角色名称" min-width="150" />
        <el-table-column prop="code" label="角色编码" min-width="170" />
        <el-table-column prop="remark" label="备注" min-width="180">
          <template #default="{ row }">
            <span v-if="row.remark">{{ row.remark }}</span>
            <span v-else class="muted">—</span>
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
        <el-table-column label="操作" width="210" fixed="right">
          <template #default="{ row }">
            <el-button v-permission="'role:perm'" link type="warning" @click="openPerm(row)">
              分配权限
            </el-button>
            <el-button v-permission="'role:update'" link type="primary" @click="openEdit(row)">
              编辑
            </el-button>
            <el-button v-permission="'role:delete'" link type="danger" @click="onDelete(row)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 新增 / 编辑 -->
    <el-dialog v-model="dialog" :title="form.id ? '编辑角色' : '新增角色'" width="480px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="角色名称" prop="name">
          <el-input v-model.trim="form.name" maxlength="64" />
        </el-form-item>
        <el-form-item label="角色编码" prop="code">
          <el-input
            v-model.trim="form.code"
            maxlength="64"
            placeholder="字母开头，仅字母/数字/下划线/横线"
          />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" :rows="2" maxlength="255" />
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

    <!-- 权限分配 -->
    <el-drawer v-model="permDrawer" :title="`分配权限：${currentRole?.name || ''}`" size="460px">
      <el-alert
        class="perm-tip"
        type="info"
        :closable="false"
        show-icon
        title="勾选菜单与按钮权限点；菜单会自动呈半选状态表示「部分权限」。保存为覆盖式提交。"
      />
      <div v-loading="permLoading" class="perm-tree">
        <el-tree
          ref="menuTreeRef"
          :data="menus"
          node-key="id"
          show-checkbox
          default-expand-all
          :props="{ label: 'name', children: 'children' }"
        >
          <template #default="{ data }">
            <span class="perm-node">
              {{ data.name }}
              <el-tag v-if="data.perm" size="small" effect="plain" type="info">{{ data.perm }}</el-tag>
            </span>
          </template>
        </el-tree>
      </div>
      <template #footer>
        <el-button @click="permDrawer = false">取消</el-button>
        <el-button type="primary" :loading="assigning" @click="onAssign">保存</el-button>
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
import { nextTick, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import {
  menuTree,
  roleAssignMenus,
  roleCreate,
  roleDelete,
  roleList,
  roleMenuIds,
  roleUpdate,
} from '@/api'

const list = ref([])
const loading = ref(false)
const keyword = ref('')

const dialog = ref(false)
const saving = ref(false)
const formRef = ref(null)

const permDrawer = ref(false)
const permLoading = ref(false)
const assigning = ref(false)
const menuTreeRef = ref(null)
const menus = ref([])
const currentRole = ref(null)

const form = reactive({
  id: null,
  name: '',
  code: '',
  remark: '',
  enabled: true,
})

const rules = {
  name: [{ required: true, message: '请输入角色名称', trigger: 'blur' }],
  code: [
    { required: true, message: '请输入角色编码', trigger: 'blur' },
    {
      pattern: /^[A-Za-z][A-Za-z0-9_-]*$/,
      message: '编码需以字母开头，仅允许字母、数字、下划线、横线',
      trigger: 'blur',
    },
  ],
}

async function load() {
  loading.value = true
  try {
    list.value = await roleList({ keyword: keyword.value || undefined })
  } finally {
    loading.value = false
  }
}

function openCreate() {
  Object.assign(form, { id: null, name: '', code: '', remark: '', enabled: true })
  dialog.value = true
}

function openEdit(row) {
  Object.assign(form, {
    id: row.id,
    name: row.name,
    code: row.code,
    remark: row.remark || '',
    enabled: row.enabled,
  })
  dialog.value = true
}

async function onSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  const payload = {
    name: form.name,
    code: form.code,
    remark: form.remark || null,
    enabled: form.enabled,
  }

  saving.value = true
  try {
    if (form.id) {
      await roleUpdate(form.id, payload)
      ElMessage.success('角色已更新')
    } else {
      await roleCreate(payload)
      ElMessage.success('角色已创建')
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
    await ElMessageBox.confirm(
      `确认删除角色「${row.name}」？若仍被用户使用，删除将被拒绝。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return // 用户取消
  }

  try {
    await roleDelete(row.id)
    ElMessage.success('角色已删除')
    await load()
  } catch {
    // 错误提示由拦截器处理
  }
}

/** 收集叶子节点 ID：回显时只勾叶子，父节点由 el-tree 自动置为半选 */
function collectLeafIds(nodes) {
  return nodes.flatMap((node) =>
    node.children?.length ? collectLeafIds(node.children) : [node.id],
  )
}

async function openPerm(row) {
  currentRole.value = row
  permDrawer.value = true
  permLoading.value = true
  try {
    const [tree, assignedIds] = await Promise.all([menuTree(), roleMenuIds(row.id)])
    menus.value = tree
    await nextTick()
    const leafSet = new Set(collectLeafIds(tree))
    menuTreeRef.value?.setCheckedKeys((assignedIds || []).filter((id) => leafSet.has(id)))
  } catch {
    // 错误提示由 axios 拦截器统一处理
  } finally {
    permLoading.value = false
  }
}

async function onAssign() {
  const treeRef = menuTreeRef.value
  if (!treeRef || !currentRole.value) return

  // 提交「选中 + 半选」：半选节点是目录/菜单，保存后回显才准确
  const menuIds = [...treeRef.getCheckedKeys(), ...treeRef.getHalfCheckedKeys()]

  assigning.value = true
  try {
    await roleAssignMenus(currentRole.value.id, { menuIds })
    ElMessage.success('权限已保存')
    permDrawer.value = false
  } catch {
    // 错误提示由 axios 拦截器统一处理
  } finally {
    assigning.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.muted {
  color: #c0c4cc;
}

.perm-tip {
  margin-bottom: 12px;
}

.perm-tree {
  max-height: calc(100vh - 220px);
  overflow: auto;
}

.perm-node {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
</style>
